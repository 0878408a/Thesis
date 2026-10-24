# Manufacturer Agent V2 Performance 修復與完整驗證

日期：2026-10-06。k6 全程在 Kubernetes 內執行，走 `https://nginx:8443/manufacturer/agent/...` 與有效 mTLS client identity，沒有使用 port-forward。

## 1. Root Cause

**Layer 1 — Werkzeug single worker：confirmed。** `run_manufacturer_agent.py` 的 production branch 原先呼叫 `werkzeug.serving.run_simple()`；Pod runtime 是一個 `python run_manufacturer_agent.py`，沒有 Gunicorn worker。Werkzeug `run_simple` 預設非 threaded；在同一路徑下，10→100 VU 時 RPS 從 18.39 降至 14.79，而 p95 從 1.03s 升至 13.58s。改成 Gunicorn 2 workers 後，100 VU RPS 提升到 31.29、p95 降至 6.80s，符合單 worker queue/head-of-line 限制的證據。

**Layer 2 — synchronous IOTA：confirmed。** Upload view 原先同步呼叫 `subprocess.run(npx tsx submit_firmware.ts)`；IOTA 外部等待在 HTTP worker request lifecycle 內。有效 mTLS upload 曾等 60.453s 後由 Nginx 回 504，但 firmware row 隨後已取得真實鏈上 object，直接造成「客戶收到失敗、鏈上其實成功」的不一致。獨立 worker 上線後，實測 IOTA 背景耗時 52.038s，而穩定部署後 upload API 在 4.219s / 4.801s 回 HTTP 202 `accepted`。

**不是這次根因：mTLS trust failure、IOTA GIL contention、MariaDB connection-limit exhaustion。** mTLS business path 已驗證；MariaDB slow query 為 0、`Max_used_connections=18/151`。30 分鐘 soak 的 DB traceback 是 TCP connect timeout，伴隨 Docker Desktop node CPU 約 92–93%，指向本機單節點資源/網路排程容量限制，而非 IOTA 或 TLS。

## 2. mTLS

- Root CA：`thesis/ca/certs/ecdsa_ca.pem`，自簽 `ISU_Root_CA`，效期 2025-06-23 至 2035-06-21。Nginx 實際掛載的 `client_ca.pem` SHA-256 指紋與此 CA 相同。
- Nginx server cert：CN `localhost`，SAN `localhost`、`nginx`、`127.0.0.1`，效期 2026-09-23 至 2036-09-21；`openssl verify` 與 `openssl s_client -verify_return_error` 均回 `OK` / return code 0。
- Manufacturer client cert：CN `manufacturer.example.com`，issuer 為同一 Root CA，效期 2026-03-26 至 2036-03-23；`openssl verify` 回 `OK`。Kubernetes Manufacturer Client secret cert 指紋與 repo 既有 cert 相同；以它實際呼叫 History 成功回 HTTP 200。
- k6 從 `thesis-manufacturer-client-certs` secret 掛載既有 client cert/private key，`tlsAuth` 提供 client identity，`SSL_CERT_FILE=/certs/ecdsa_ca.pem` 驗證 server chain；沒有跳過 TLS 驗證。in-cluster k6 2.2.0 的 1 VU smoke 為 75/75 HTTP 2xx、0% request failure、150/150 checks pass，response body 有 `count/results`。
- Nginx 實際 `ssl_client_certificate /etc/nginx/certs/client_ca.pem`、`ssl_verify_client on`；上游仍為 `http://manufacturer-agent:8000/`。無 client cert 的探測得到 Nginx `400 No required SSL certificate was sent`；有效 client cert 的 business request 回 200/202。mTLS termination 架構未改。

## 3. 修改檔案

| 檔案 | 變更 |
|---|---|
| `thesis/manufacturer_agent/run_manufacturer_agent.py` | Production plain-HTTP branch `os.execv` 成 Gunicorn，預設 2 sync workers、`--pythonpath /app`；本機 `ENABLE_MTLS=1` 開發分支保留。 |
| `thesis/manufacturer_agent/upload_firmware/views.py` | Upload transaction 同時保存 metadata 與 pending submission row；HTTP request 不再呼叫 IOTA；response 回 202/accepted；History 增加 status/object ID 遮罩；IOTA helper 回傳 object/result 給 worker。 |
| `thesis/manufacturer_agent/upload_firmware/management/__init__.py`、`commands/__init__.py` | Django management command package markers。 |
| `thesis/manufacturer_agent/upload_firmware/management/commands/process_iota_submissions.py` | DB-backed worker；MySQL advisory lock 防止多 worker 重複領取；成功更新為真 object ID，失敗記錄 failed 狀態；記錄實際 IOTA elapsed time。 |
| `Dockerfile.manufacturer-agent` | 未修改；原 CMD 進入 runner，runner 現在 `exec` 為 Gunicorn。 |
| `k8s_v2/deployments/manufacturer-iota-worker.yaml` | 新增單一 worker Deployment，復用 Agent image/DB/IOTA secret，graceful termination 400 秒。 |
| `docker-compose.yml` | 新增 `manufacturer-iota-worker` service，復用 Agent service 設定，stop grace 7 分鐘。 |
| `thesis/manufacturer_client/frontend/manufacturer/src/App.tsx`、`src/components/UploadStatus.tsx`、`App.css` | 202 accepted 顯示 Processing，不把接受工作冒稱 IOTA success。 |
| `thesis/manufacturer_client/frontend/manufacturer/src/components/FirmwareHistory.tsx` | History 輪詢 pending rows，顯示 Pending/Uploaded/Failed，只對真 object ID 建立 explorer link。 |
| `thesis/manufacturer_agent/upload_firmware/tests.py`、`tests_concurrency.py` | 202 contract、worker success/failure、競爭衝突 assertion；fixture 用唯一版本，並安全使用專用 concurrency test DB。 |
| Manufacturer Client 的 `App.test.tsx`、`FirmwareHistory.test.tsx` | 覆蓋 accepted/pending/failed 狀態。 |
| `docs/V2_ARCHITECTURE.md` | 記錄獨立 IOTA worker 與狀態合約。 |
| `thesis/load_tests/manufacturer-history-test.js` | 改成 in-cluster mTLS k6，有 2xx/4xx/5xx/other、response body、checks、p50/p90/p95/p99/max summary。 |

未改 `nginx.conf`、Nginx mTLS ConfigMap、Customer Agent、`requirements.txt`、Manufacturer DB migration；本機映像已重建並部署。`k8s_v2/deployments/manufacturer-agent.yaml` 與其他工作樹內容在開始前已有使用者修改，本次未改動其 resource/replica 區塊。

## 4. DB

**DB schema changed: NO.** Existing `SubmitBlockRecord` schema reused; no new DB columns were added.

實際 DDL 仍只有 `object_id varchar(66) NOT NULL PRIMARY KEY`、`metadata_id`、`submit_block_result`。因 `object_id` 是 `NOT NULL` primary key，不能依需求直接寫 SQL NULL；使用現有欄位的內部 key `pending:<metadata_id>` / `failed:<metadata_id>` 表示狀態。History serializer 隱藏這些 sentinel，只有成功時回傳鏈上 object ID。FirmwareMetadata 與 pending row 在同一 DB transaction 寫入；worker 成功以 object ID 原子替換 placeholder。部署後查得 pending=0、failed=0。

## 5. API

- `accepted`：`POST /upload_firmware/upload/` 回 HTTP 202，保留原 `UploadResult`、Message、Errorcode 與 response signature，新增 `status: accepted`、`metadata_id`；代表 firmware 已持久化、IOTA 尚待背景處理。
- `success`：History API 回 `status: success` 與真實 `object_id`，代表 worker 已取得鏈上 object。
- `failed`：worker 重試耗盡後，History API 回 `status: failed`、空 `object_id`，錯誤摘要存於既有 `submit_block_result`；不新增 status/error columns。

## 6. Test Results

**mTLS verification：PASS。** 有效 cert 的 k6 smoke 全部 2xx；無 client cert 由 Nginx 回 400，沒有把 TLS 拒絕路徑納入效能數據。

**Backend tests：PASS。** Django 原生 `python manage.py test upload_firmware.tests`：27/27 passed。獨立 `tests_concurrency.py`：在專用 `v2_concurrency_test_db` 以 pytest 執行，2/2 passed（20 concurrent same-version uploads 只有 1 個 202、19 個 409）。直接 pytest `tests.py` 在本環境缺 `pytest-django`，因此使用 Django test runner 執行完整 27 項。

**Related tests：PASS。** Manufacturer Client pytest 25/25；Manufacturer Frontend Vitest 54/54，`npm run build` 成功；Django API/worker `manage.py check` 均無問題；`docker compose config -q` 與新 worker manifest dry-run 通過。

**In-cluster k6 mTLS short tests：**

| 階段 | VU | requests | RPS | p50 | p95 | p99 | max | http_req_failed | 2xx / 4xx / 5xx / other |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Before: Werkzeug | 10 | 2,213 | 18.39 | 345ms | 1.03s | 6.26s | 13.45s | 0% | 2,213 / 0 / 0 / 0 |
| Before: Werkzeug | 50 | 2,392 | 19.39 | 1.62s | 6.55s | 7.96s | 8.68s | 0% | 2,392 / 0 / 0 / 0 |
| Before: Werkzeug | 100 | 1,925 | 14.79 | 5.48s | 13.58s | 15.76s | 18.12s | 0% | 1,925 / 0 / 0 / 0 |
| Phase 1: Gunicorn 2 | 10 | 3,243 | 26.97 | 304ms | 853ms | 1.21s | 7.67s | 0% | 3,243 / 0 / 0 / 0 |
| Phase 1: Gunicorn 2 | 50 | 3,559 | 29.23 | 1.19s | 3.74s | 13.89s | 17.63s | 0% | 3,559 / 0 / 0 / 0 |
| Phase 1: Gunicorn 2 | 100 | 3,927 | 31.29 | 2.75s | 6.80s | 8.93s | 10.56s | 0% | 3,927 / 0 / 0 / 0 |
| Phase 2: async IOTA | 10 | 2,266 | 18.83 | 417ms | 1.17s | 1.87s | 7.94s | 0% | 2,266 / 0 / 0 / 0 |
| Phase 2: async IOTA | 50 | 2,819 | 22.60 | 1.68s | 5.32s | 12.14s | 13.04s | 0% | 2,819 / 0 / 0 / 0 |
| Phase 2: async IOTA | 100 | 2,636 | 21.15 | 3.88s | 9.01s | 11.22s | 12.72s | 0.04% | 2,635 / 0 / 0 / 1 |

Phase 2 100 VU 的單一 `other` 是 k6 20s client request timeout，沒有 HTTP status；該 run 的 checks 5,270 passed / 2 failed。Node CPU 在這輪達約 93%，HPA 到 4 replicas。此 mTLS k6 測試在 cluster 內，不含 port-forward 限制。Phase 2 的 History API 不執行 IOTA，故短測波動不應解讀為 async 導致或解決 History DB 容量。

**30-minute soak（Phase 2, 50 VU）：FAIL under this single-node capacity.** `thesis/load_tests/results/v2/manufacturer-after-phase2-soak30.out`：30m、30,705 requests、17.04 RPS、p50 2.267s、p90 5.649s、p95 7.165s、p99 11.305s、max 21.215s；30,603 2xx、0 4xx、10 5xx、92 timeout/no-status，合計 `http_req_failed=0.33%`，0 interrupted iterations。Nginx 記錄 client-abandoned 499；Django 500 traceback 是 `OperationalError (2002) Can't connect to server on manufacturer-mariadb (115)`。同期 Docker Desktop node CPU 約 92–93%，HPA 已到 max 4；MariaDB `Max_used_connections=18/151`、`Slow_queries=0`，因此目前證據較支持單節點 CPU/network scheduling 飽和，而非 SQL 慢查詢、連線數上限、mTLS 或 IOTA。這是本次明確保留的容量失敗，不視為功能測試全通過。

## 7. Before / After

```text
Before
Nginx :8443 (mTLS) → HTTP → Django WSGI → Werkzeug run_simple → 1 process / default non-threaded
POST upload → same request worker waits for npx/tsx → IOTA → response (observed 504 at 60.453s)

Phase 1
Nginx :8443 (mTLS) → HTTP → Gunicorn master → 2 sync workers → Django WSGI

Phase 2
Nginx :8443 (mTLS) → HTTP → Gunicorn (2 workers)
    → DB transaction: FirmwareMetadata + pending SubmitBlockRecord → HTTP 202 accepted
Independent worker → advisory lock → npx/tsx → IOTA → update existing object_id/result
```

同路徑 100 VU 短測的 Before→Phase 1：RPS 14.79→31.29（約 2.1x），p95 13.58→6.80s；Phase 2 100 VU History read 為 21.15 RPS / p95 9.01s，且有 1 client timeout，受同一單節點資源上限影響。

IOTA request lifecycle 的 Before→Phase 2 實證：同步路徑 HTTP 60.453s 後 504，但鏈上最終成功；穩定 Phase 2 upload HTTP 4.219s / 4.801s 回 `202 accepted`，IOTA 背景耗時 52.038s，三筆測試 firmware 最終都在 History 顯示 success 並有真 object ID。背景成功不再占住 HTTP worker。

## 8. HPA

**PASS — dynamic scaling experimentally verified.** HPA 設定 min=3/max=4、CPU target 75%；k6 高併發期間有 `SuccessfulRescale: New size: 4; reason: cpu resource utilization above target`，並實際由 3→4。soak 中維持 4；測試期間曾量到約 49–79%/75%，最後負載停止後回到 0%/75%，replicas 因 downscale stabilization 暫留 4。metrics-server 曾間歇回 `<unknown>`，但沒有抹除已觀測到的成功 scale event；這個量測不穩定仍需留意。

## 9. Remaining Risks

1. 單一 Docker Desktop node 在 50 VU 持續 30 分鐘出現 0.33% failure；100 VU 短測也出現一次 client timeout。Node CPU 92–93%、HPA 到 max=4，超出本次只調 WSGI/IOTA 的範圍；需另行處理本機叢集容量/DB network 壓力，不能以提高 HPA replicas 假定可解決。
2. IOTA worker 目前單副本、一次處理一筆；本次量到一筆約 52s。大量連續 uploads 會形成 DB-backed pending backlog；最終 retry exhausted 會標 failed，沒有自動 redrive endpoint。
3. IOTA 已成功但 worker 在 object ID 寫回 DB 前被強制終止，重啟後可能重送，因鏈上呼叫與本地 DB commit 不能形成跨系統原子交易。400s termination grace 降低此窗口，但不能消除 process/node abrupt loss。
4. HPA metrics-server 有間歇性 no-metrics warning；即使動態 scale 已實驗成功， metrics collection 在本機叢集並非完全穩定。
5. soak 的 Django 500 發生時部署 `DJANGO_DEBUG=True`，Nginx 觀察到約 266KB debug response；此值未在本次改動，會放大錯誤流量並暴露 traceback，宜另案改成 production-safe setting。
6. 專用 concurrency test 必須用 `.env` 提供 DB password；本次已強制指向 `v2_concurrency_test_db`，不再嘗試刪共用 `mydatabase` 的 Device/Firmware rows。

## 10. Git 狀態

- 本次修改：Gunicorn startup、IOTA API/worker、Compose worker service、K8s worker manifest、Manufacturer UI states/tests、API tests、architecture notes、mTLS k6 script/results。
- 新增部署/worker 檔：`k8s_v2/deployments/manufacturer-iota-worker.yaml`、`thesis/manufacturer_agent/upload_firmware/management/commands/process_iota_submissions.py` 與 management package markers。
- 測試 artifacts：Before/Phase 1/Phase 2 VU output、30 分鐘 soak output；未提交、未 commit。
- 未修改 Nginx mTLS ConfigMap/設定；worker 部署已同步至 `k8s_v2/` 與 Compose。
- Worktree 在開始前已存在其他修改/大量 untracked 檔案（例如 Customer Agent、HPA/resource manifests、V2 報告、憑證、OpenSpec 等），均保留未回復、未 commit。`git diff --check` 只指出既有 `V2_IMPLEMENTATION_REPORT.md` 的兩行 trailing whitespace，本次未碰該檔。
- DB schema changed: **NO**。
