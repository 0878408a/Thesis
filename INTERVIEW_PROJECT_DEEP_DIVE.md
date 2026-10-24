# Interview Project Deep Dive

> **Purpose.** 這份文件不是「教材」，而是從 `Thesis` repository 實際 source code 出發，
> 把「面試官可以從這個專案一路深挖到什麼程度」完整盤點。
> 每一份事實都附上「repository 證據」（file path），沒有證據的部分明確標 [GENERAL]。
> 本文件是 READ / ANALYZE / REPORT 產出物，未修改任何 source / K8s / Docker / CI / 測試檔。
>
> 標記系統：
> - `[IMPLEMENTED]` = 在 repo 裡可找到對應程式碼 / 配置
> - `[VERIFIED]` = 有已提交的測試 / 報告 / k6 結果佐證
> - `[PLANNED]` = 有意圖但尚未見於 repo（例如未做 HPA dynamic scaling k6 驗證）
> - `[GENERAL]` = 教科書 / 通用知識，repo 未直接證據（用於回答 follow-up）

---

## 1. Executive Summary

這個專案是「IoT 安全韌體更新（Secure OTA）」研究，核心是讓 **manufacturer** 上傳韌體並上鏈
（IOTA testnet + Move），**customer** 透過 customer-agent 偵測上鏈事件並完成 OTA。
整條鏈以 **mTLS / PKI** 作為信任邊界，以 **Nginx** 做 TLS 終端，以 **Docker** 開發、
**Kubernetes（V2）** 做部署，以 **CI/CD** 做自動化驗證，並以 **k6** 做效能驗證。

**一句話可背：**
> 「這是一個把『智慧合約（IOTA Move）＋數位簽章（ECDSA/RSA）＋mTLS（Nginx / OpenSSL）＋
> 資料庫併發控制（MariaDB unique constraint + atomic）＋容器化（Docker→K8s）＋效能工程（k6）』
> 串成一條可驗證 OTA 資安鏈的端到端專案；我的角色是把每一環的『為什麼這樣設計、會怎麼壞、怎麼驗證』講清楚。」

**V2 最終狀態（2026-10-07 確認）：**
1. **Async IOTA Worker**：Upload API 回應 202，獨立 worker 處理 IOTA 上鏈，K8s 1/1 Running，0 restarts，DB pending=0 / success=4。
2. **HPA 1→2→3 已實際觀察到 [VERIFIED]**：k6 50 VU / 3m 觸發 rescale，`SuccessfulRescale New size: 2` 和 `New size: 3` 均記錄於 `latest/hpa/hpa-scaling-events.txt`。
3. **最新 30-min soak：45,664 requests / 0% 失敗 [VERIFIED]**（`latest/soak/soak-50vu-30m.txt`），對比歷史 Phase 2 soak 0.33% 失敗（`thesis/load_tests/results/v2/manufacturer-after-phase2-soak30.out`）。
4. **`DJANGO_DEBUG` 已由 "True" 改為 "False" [IMPLEMENTED][VERIFIED]**（K8s manifest），mTLS smoke 驗證通過。
5. **`k8s-manifest-validate` 已涵蓋 V2 [IMPLEMENTED]**（`k8s_v2/` 全目錄 dry-run）。

**誠信點（要主動講）：**
1. metrics-server 有**間歇性 kubelet scrape timeout**（10s），HPA 在 metrics 可讀時正常觸發 rescale；**Metrics Server = CONDITIONAL**，非完全 PASS。
2. 執行環境為**單節點 Docker Desktop K8s**（4 CPU），所有效能數據受此限制；多節點行為無法驗證。
3. 歷史 0.33% soak 與本次 0% soak **執行條件不同，不可直接比較**；本次為正式結果。
4. V1 的 `mariadb` Pod 在集群上仍未刪除（V2 已改用 `customer-mariadb` / `manufacturer-mariadb`）。

**專案規模（證據）：**
- 後端 3 個 Python service：`customer_agent`（Flask）、`manufacturer_agent`（Django REST）、`manufacturer_client`（Flask）
- 前端 2 支 React 19 + Vite + Vitest 應用
- K8s V2：12+ 份 YAML（6 Deployment + 2 PVC + HPA + Job + ConfigMap + namespace + metrics-server + IOTA worker）
- CI：4 條 workflow（test.yml 涵蓋 Django/worker/concurrency/frontend/k8s manifest）
- 測試：customer_agent pytest、manufacturer_client pytest、transfer_firmware 21 tests、mTLS 6 tests、frontend Vitest、k6 V1/V2

---

## 2. Repository Architecture

**Evidence（top-level）：**

```
thesis/
  customer_agent/         Flask, 雙埠 (PUBLIC=5001, DEVICE=5000) + webhook + query pipeline + telegram
  manufacturer_agent/     Django + DRF, /upload_firmware + /transfer_firmware, IOTA submit
  manufacturer_client/    Flask internal (:5002), 透過 mTLS 端點 upload / 讀 history
  shared/config.py        所有憑證路徑、API URL、IOTA 腳本路徑（CERT_DIR 可覆蓋）
  firmware_module/        Move.toml + sources/firmware_module.move (IOTA on-chain module)
  load_tests/             k6 load-test.js + soak_monitor.py + results/{v1,v2}/
  ca/certs/               自簽 CA、full chain
nginx/                    nginx.conf + conf.d/{customer,manufacturer}.conf + certs
k8s_v2/                   namespace + 2 pvc + configmaps + 6 deployments + hpa + jobs
docker/                   initdb SQL / seed scripts
Dockerfile.{customer-agent,manufacturer-agent,manufacturer-client}
docker-compose.yml
```

**Architectural decisions（可背）：**
1. **拆分 3 個 service 而非 monolith**：customer（瀏覽器 / 裝置端）、manufacturer agent（Django API + IOTA）、manufacturer client（上傳 / 歷史讀取）。邊界 = 信任域。
2. **Nginx 是 single entry point**：443（customer HTTPS + static SPA）、8443（manufacturer mTLS）。上游一律 plain HTTP，mTLS 在 8443 終結（`conf.d/manufacturer.conf`：`ssl_verify_client on`）。
3. **Flask vs Django 混用是刻意**：customer_agent 用 Werkzeug `make_server`（輕、雙埠、mTLS 易掌控）；manufacturer_agent 用 Django REST（ORM / 事務 / admin / migration 成熟）。
4. **憑證可用 `CERT_DIR` env 重映射**（`shared/config.py` + `customer_agent/config.py`），讓 Docker 從 volume 掛入而非 bake 私鑰進 image。

**Follow-up depth（面試官可問到）：** 為什麼不用微服務全拆？→ 信任域不同；customer 要「雙埠（browser vs ESP32 device）」；agent 要「DB 事務 + IOTA subprocess」。

---

## 3. Technology Inventory

| Domain | Technology | Evidence | Status |
|---|---|---|---|
| Backend (customer) | Flask + Werkzeug `make_server` | `customer_agent/webhook.py`、`run_customer_agent.py` | [IMPLEMENTED] |
| Backend (manufacturer) | Django + DRF | `manufacturer_agent/`、`core/settings.py` | [IMPLEMENTED] |
| DB | MariaDB (mysqlclient / pymysql) | `core/settings.py`、`customer_agent/db.py` | [IMPLEMENTED][VERIFIED] |
| On-chain | IOTA testnet + Move + `@iota/iota-sdk` (tsx) | `firmware_module/`、`upload_firmware/submit_firmware.ts` | [IMPLEMENTED] |
| Crypto | ECDSA (P-256) / RSA (4096), SHA-256, cryptography lib | `views.py`、`verify.py`、`shared/config.py` | [IMPLEMENTED] |
| mTLS / PKI | 自簽 CA + 客戶 / 伺服器 cert | `ca/certs/`、`nginx/conf.d/` | [IMPLEMENTED] |
| TLS termination | Nginx 1.27-alpine | `nginx/nginx.conf` | [IMPLEMENTED] |
| Container | Docker (3 Dockerfiles + frontend) | `Dockerfile.*`、`docker-compose.yml` | [IMPLEMENTED] |
| Orchestration | Kubernetes V2 (12 YAML + metrics-server) | `k8s_v2/` | [IMPLEMENTED][VERIFIED]（metrics-server 部署 + 3-pod baseline；HPA dynamic scaling 待壓測） |
| CI/CD | GitHub Actions (4 workflows, GHCR) | `.github/workflows/` | [IMPLEMENTED] |
| Frontend | React 19 + Vite + TS + Vitest | `customer_agent/frontend/customer/`、`manufacturer_client/frontend/manufacturer/` | [IMPLEMENTED][VERIFIED] |
| Load / Perf | k6 v2 + soak monitor | `load_tests/` | [IMPLEMENTED][VERIFIED] |
| Device | ESP32 (mDNS + TLS download) | `blink.ino`、`no_blink.ino`、`run_customer_agent.py` mDNS | [IMPLEMENTED] |
| Notification | Telegram webhook | `telegram_notify.py`、`webhook.py` | [IMPLEMENTED] |
| AI Agent / OpenSpec | `.agents/`、`openspec/`、`.github/{agents,prompts,skills}` | 目錄 inventory | [IMPLEMENTED] |

---

## 4. Actual Implementation Evidence（逐行級）

> 以下只列「我實際讀過的 file + 行號」，作為後續每個 Deep Dive 的錨點。

- **Flow A（Upload）：** `upload_firmware/views.py` L348–L680（完整讀過）；`models.py` `unique_together`；`submit_firmware.ts` L1–L210（完整讀過）；`firmware_module.move` `publish`（完整讀過）。
- **Flow B（History）：** `views.py` `HistoryListAPIView` + `SubmitBlockRecordHistorySerializer`（L560–L620 區間）。
- **Flow C（OTA）：** `customer_request.py` L1–L190（完整讀過）；`webhook.py` L1–L120；`query.py`（pipeline）；`db.py` L1–L120；`run_customer_agent.py` L1–L220。
- **Flow D（mTLS）：** `nginx/nginx.conf` + `conf.d/customer.conf` + `conf.d/manufacturer.conf`（完整讀過）；`customer_agent/config.py`（完整讀過）。
- **Flow E（DB 併發）：** `views.py` L580–L640（`transaction.atomic()` + `IntegrityError`）；`models.py`；`tests_concurrency.py`。
- **Flow F（IOTA）：** `submit_firmware.ts`（完整）；`firmware_module.move`（完整）；`Move.toml`（完整）。
- **Flow G（Docker→K8s）：** 3 支 Dockerfile + `docker-compose.yml`（subagent 證據）；`k8s_v2/`（subagent 證據，全 12 YAML）。
- **Flow H（CI/CD）：** 4 支 workflow（subagent 證據）。
- **Flow I（Frontend）：** 兩支 React app（subagent 證據 + 我讀的 `customer/src`）。
- **Flow J（Testing）：** `load_tests/load-test.js` L143–L152 thresholds；`results/v2/k6_soak30.json` + `results/v1/k6_soak30.json`（完整讀過）。

---

## 5. Firmware Upload Deep Dive（Flow A）

**What / How（`upload_firmware/views.py` `UploadFirmwareAPIView.post`）：**
1. 解析 `firmware_data`（base64）與 `metadata`（dict）。
2. 逐欄位驗證：缺失 / 格式 → 回 `metadata_error_code`（1001/1011/3001…）。
3. `is_valid_base64` 驗證簽章與 firmware 皆為合法 base64。
4. `uuid.UUID` 驗證 `manufacturer_id`；查 `Manufacturer` / `Device` 是否存在（FK 約束）。
5. NTP timestamp 驗證：`release_date` 必須介於「DB 最新」與「now + ALLOWED_TIME_DRIFT(10s)」之間。
6. `existing_version = FirmwareMetadata.objects.filter(...).exists()` → 若已存在回 **HTTP 409**（`3042`）。
7. `verify_signature` 驗證 metadata + firmware 簽章（RSA→PKCS1v15 / ECDSA→ECDSA(SHA256)）。
8. `with transaction.atomic(): FirmwareMetadata.objects.create(...)` 包住 INSERT。
9. `except IntegrityError → 409`（併發最終保護）；`except Exception → 5002`。
10. `upload_to_blockchain(firmware_metadata)` 上鏈；成功回 200（signed response），失敗回 500。

**Why：** `exists()` 是「快速路徑」（避免無謂 INSERT），`transaction.atomic()` + DB `unique_together` 是「正確性路徑」（check-then-insert 的 race 由唯一約束最終擋住）→ 兩層防禦。

**Risk / Limitation：**
- `ALLOWED_TIME_DRIFT=10s` 是「client clock vs server clock」的容忍；若 NTP 未同步會誤拒。
- IOTA 上鏈在**事務外**（`with transaction.atomic()` 已出）：DB 已寫、上鏈失敗 → 500 但 DB 保留（by design，方便手動重試），但這表示「DB 成功 ≠ 上鏈成功」，需要 reconciliation。
- `verify_signature` 的 `except Exception` 吞掉具體錯誤只回 False（debug 用 print，非 log）。

**Test：** `tests_concurrency.py`（20 併發同版本 → 1×200/201 + 19×409；sequential dup → 409；DB count==1）[IMPLEMENTED][VERIFIED 前次 session 2/2]。

**Follow-up tree：**
- 「為什麼用 409 而非 400？」→ Conflict 語意正確（resource 已存在）；client 可判「duplicate」。
- 「check-then-insert race 怎麼保證？」→ 靠 DB `UNIQUE(manufacturer_id, device_type, firmware_version)` + `IntegrityError`；`.exists()` 只是 fast-path。
- 「上鏈失敗但 DB 已寫，怎麼辦？」→ outbox / 手動重試；目前 [PLANNED] 無自動 reconcile。
- 「firmware 太大怎麼辦？」→ LONGBLOB base64；`client_max_body_size 20M`（nginx）。
- 「簽章是 metadata 與 firmware 分開，為什麼？」→ firmware 本體可能很大，分開簽可只簽 hash；這裡直接簽整個 binary。

---

## 6. Firmware Query Deep Dive（Flow B — History API）

**How（`views.py` `HistoryListAPIView`）：**
- `GET /upload_firmware/history/` → `SubmitBlockRecord.objects.select_related('metadata_id').order_by('-metadata_id__release_date')`
- `select_related` 避免 N+1；`StandardResultsSetPagination`（page_size=10, max=100）。
- serializer 把 `SubmitBlockRecord` JOIN `FirmwareMetadata` 的 `firmware_version / device_type / firmware_size / release_date` 攤平輸出。

**Why：** 上鏈成功才 `SubmitBlockRecord.objects.create(object_id, metadata_id, result)`；history 只列「已上鏈」的紀錄，代表「上鏈成功的事實」。

**Limitation：** 沒有 filter（只能分頁排序）；沒有 cache；`release_date` 是 NTP 不是 ISO。

**Follow-up：** 「為什麼 history 用 SelectRelated 而非 prefetched？」「分頁游標 vs offset？」「如果 metadata 被刪了？（FK + `select_related` 會拿不到 → 需 on_delete 策略）」。

---

## 7. Customer OTA Deep Dive（Flow C）

**End-to-end（`customer_agent/`）：**
- `run_customer_agent.py`：多執行緒啟動 **public HTTPS server（5001）** + **mTLS device server（5000）** + **每 3s 的 `run_periodic_query`** + **mDNS 廣播**（`customer-agent.local`）。
- `query.py`（pipeline）：向 IOTA 偵測新上鏈 `FirmwareEvent` → 寫入本地 `firmwaremetadata`（`db.insert_firmware_metadata`）→ 觸發 `get_customers_by_firmware` 找出「該 manufacturer + device_type 且版本未更新」的 customer → Telegram 通知（`telegram_notify.py`）。
- `webhook.py`：Telegram button callback（`install_fw:<cid>:<ver>`）→ `customer_request.py` 下指令。
- `customer_request.py`：用 **mTLS**（`requests.post(..., cert=(customer cert, key), verify=CA)`）向 `manufacturer_agent /transfer_firmware/request_download/` 發簽章請求 → 驗證回應簽章 → 下載 firmware binary → 用 `firmware_signature` 驗證本體 → `save_firmware_binary` 寫 DB。
- `db.py`：純 `pymysql`（**每次 `get_db_connection()` 都 `pymysql.connect()`，with block 關連線**）→ **無 connection pool**（刻意輕量）。

**Why single-threaded + 無 pool：** customer_agent 是「邊緣 / 裝置側」agent，QPS 低；Flask `make_server` 預設 single-threaded；DB 連線「用完即關」避免在邊緣累積連線。

**Risk / Limitation：**
- **GIL contention**：`run_periodic_query`（每 3s 對外 IOTA HTTP）與 HTTP server 同 process，single-threaded Werkzeug → 高併發時阻塞（k6 V2 soak 21.1% timeout 的懷疑因素之一，未完全隔離）。
- 無 pool → 每個 query 都開新 TCP 連線（TIME_WAIT 累積，Docker port-forward 下放大）。

**Follow-up：** 「為什麼不用 Gunicorn / 多 worker？」「pymysql 無 pool 在 QPS 高時？」「每 3s 輪詢 IOTA vs subscribe 事件？」「mDNS 失敗時裝置怎麼 discover？」「如果 IOTA testnet 慢 2.35s，pipeline 會不會落後？（會，3s 太短）」。

---

## 8. mTLS / PKI Deep Dive（Flow D）

**Trust model（證據）：**
- 自簽 CA：`ca/certs/ecdsa_ca.pem`（ECDSA / P-256；`USE_ECDSA=True`）。
- 三方憑證：customer / manufacturer-client / manufacturer-agent 各有「私鑰 + 憑證」。
- Full chain：`full_chain_manufacturer_agent.pem`、`customer_fullchain.pem`。

**Two termination points：**
1. **Nginx 8443（manufacturer 側，真 mTLS）：** `conf.d/manufacturer.conf`：
   - `ssl_certificate /etc/nginx/certs/server_cert.pem` + `ssl_certificate_key`
   - `ssl_client_certificate /etc/nginx/certs/client_ca.pem` + `ssl_verify_client on`
   - 上游 `http://manufacturer-agent:8000/`（plain HTTP）→ **mTLS 在 nginx 終結，後端不直接處理 TLS**。
2. **customer-agent device 5000（Python 端 mTLS）：** `run_customer_agent.py create_mtls_context()`：
   - `ssl.CERT_REQUIRED`；`load_verify_locations(CA_CERT_PATH + MANUFACTURER_CERT_PATH)`；`load_cert_chain(customer cert+key)` → `make_server(..., ssl_context=...)`。

**Why 兩處終結：** browser（443）是 server-only TLS；device（5000）與 nginx（8443）需「雙向」確認 peer 身分 → mTLS。

**Risk / Limitation：**
- git-tracked 自簽 cert（學術 demo）；`CERT_DIR` env 可改掛 volume，但 **image 內預設路徑仍含 .pem**（Dockerfile COPY 目錄）。
- Nginx customer 側 `proxy_ssl_verify off`（自簽，正式應 verify + CA）。

**Follow-up tree（加密 / TLS 面試核心）：**
- 「mTLS 握手步驟？」「TLS 1.2 vs 1.3 差異？」「Certificate chain 怎麼驗證？（root CA → intermediate → leaf，X509 trust anchor）」「為什麼 ECDSA P-256 而非 RSA？（簽章 / 驗章快、金鑰小、橢圓 vs RSA 安全性）」「Secp256k1 是 IOTA keypair（上鏈用），與 PKI 的 ECDSA 是不同曲線，不要混」
- 「Nginx 終結後後端是 plain HTTP，中間怎麼保證？（同 trust zone + 容器 network 隔離）」「自簽 cert 在 prod 要怎麼做？（CA 簽發 + 輪換 + CRL / OCSP）」。

---

## 9. Cryptography Deep Dive

**Algorithms（證據 `views.py` `SUPPORTED_SIGNATURE_ALGORITHMS`）：**
- RSA：`PKCS1v15 + SHA-256`（`public_key.verify(sig, data, padding.PKCS1v15(), hashes.SHA256())`）
- ECDSA：`ECDSA(SHA-256)`（**不需 padding、不傳 hash**，`public_key.verify(sig, data, ec.ECDSA(hashes.SHA256()))`）
- 別名表涵蓋 openssl / ssh / rfc / COSE（`es256`）等多種命名。

**Signing payload 格式：**
- upload response：`f"{upload_result}|{message}|{error_code_str}"` → `ManufacturerAgentSignature`（base64）。
- customer request：`f"{manufacturer_id}{device_type}{firmware_version}{customer_id}"` → `customer_signature`。
- metadata sig 原文：`firmware_size + release_date + manufacturer_id + device_type + firmware_version`。

**IOTA keypair（`submit_firmware.ts`）：** `Secp256k1Keypair`，`fromBase64(PRIVATE_KEY_BASE64).slice(1)`（去掉首 byte algo 識別）→ `getFullnodeUrl(network)`。**這與 PKI 的 ECDSA P-256 是不同用途、不同曲線**。

**Why / Limitation：**
- 簽章 payload 用 `|` 拼接而非 canonical JSON → 簡單但「欄位順序寫死」；若改格式會全部失敗。
- ECDSA 簽章是**隨機（RFC 6979 前為 k 隨機）**，同 payload 簽章結果不同（RSA-SPKI 固定）→ 不能用簽章值做 fingerprint。

**Follow-up：** 「RSA-PKCS1v15 vs PSS？」「ECDSA k 值洩漏 = 私鑰洩漏（RFC 6979 如何防）？」「為什麼 SHA-256？」「base64 vs hex 傳輸簽章？」「IOTA Secp256k1 與 Ethereum 共用，為何？」「NTP timestamp 為什麼當簽章欄位？（防重放）」。

---

## 10. Database Deep Dive

**Schemas（證據）：**
- `manufacturer_agent`（Django，MariaDB `mydatabase`）：`upload_firmware` app 有 `Manufacturer`、`Device`、`FirmwareMetadata`、`SubmitBlockRecord`；`transfer_firmware` app 有 `Customer`、`FirmwareMetadata`（FK 到 customer）。
- `customer_agent`（pymysql，`customer_database`）：`customer`、`customer_device`、`device`、`firmwaremetadata`、`manufacturer`（`customer_agent_db/*.sql`）。

**Key constraint（V2）：** `FirmwareMetadata.unique_together = ("manufacturer_id","device_type","firmware_version")`（`upload_firmware/models.py`）。`transfer_firmware` 同欄位組合（不再 `unique=True` 單欄位）。

**Why composite：** 同一 device_type 可被多 manufacturer 共用；同版本號可跨 manufacturer；只有「三者同時相同」才算 duplicate。

**Connection 管理：**
- Django：`mysqlclient` + `transaction.atomic()`；`CONN_MAX_AGE` 未在 repo 見（[GENERAL] Django 預設 0=每 request 斷）。
- customer_agent：`pymysql`，**無 pool**，每次 `connect`。

**Risk：**
- 無 migration 管理 `customer_agent` DB（純 SQL 檔案 + `docker/initdb`），schema 變更需手動。
- `LONGBLOB firmware_data` 大量資料 → history 查詢若 `select_related` 拿到整包 binary 會很貴（目前 history 只 JOIN metadata 欄位，未取 `firmware_data`，正確）。

**Follow-up：** 「為什麼不用 PostgreSQL？」「`unique_together` vs `UniqueConstraint`（可帶 condition / index）？」「`select_related` vs `prefetch_related`？」「LONGBLOB 4GB 上限？」「Django `CONN_MAX_AGE` 與 pgbouncer / mysqlc 連線池？」「Docker `--default-authentication-plugin=mysql_native_password` 為何？（mysqlclient 相容）」。

---

## 11. Concurrency Deep Dive（Flow E）

**7 個併發情境（含 3 個「未做」）：**
1. **IOTA 上鏈在 transaction 內？** → 否。`views.py` 明確 `with transaction.atomic():` 只包住 `create()`，上鏈在 `with` 外。**V2 进一步优化：IOTA 上鏈已移至獨立 Async Worker**（`manufacturer-iota-worker` deployment），HTTP API 在 ~4.2s 回 202 + 寫 pending record，worker 背景處理 IOTA（~52s）並更新 DB。
2. **client retry（同版本重傳）？** → `exists()` fast-path + `IntegrityError` 兜底 → 回 409，冪等。
3. **idempotency key / outbox？** → [PLANNED] 無。目前是「DB 保留 + 手動重試」（500 訊息寫明）。真正的 outbox pattern（DB 寫 `outbox` 表 → worker 重放）未實作。**V2 的 Async Worker 已有 MySQL advisory lock + sentinel state（`pending:<id>` / `failed:<id>`）防雙上鏈，但仍無 outbox 重放機制。**
4. 同 device 多 manufacturer 同時上傳不同版本 → 不同 key → 各成功（正確）。
5. 同 manufacturer 同 device 不同版本 → 各成功。
6. 上鏈 timeout（`IOTA_SUBPROCESS_TIMEOUT`）→ bounded retry `max_retries`（`IOTA_MAX_RETRIES`，預設 3）→ 仍失敗 raise → 500。**V2：worker 內 retry 邏輯，失敗寫 sentinel `failed:<metadata_id>`，API 不直接暴露 IOTA 失敗。**
7. 20 併發同版本（`tests_concurrency.py`）→ 1 成功 + 19×409 + DB count==1。

**Why `transaction.atomic()`：** 讓 `INSERT` 原子化；DB unique 是「最終仲裁」。若無 atomic，`create` 可能只寫一半。

**Limitation：** 沒有「optimistic locking（version 欄位）」、沒有「pessimistic lock（SELECT ... FOR UPDATE）」、沒有「分布式鎖（Redis）」（[GENERAL]，repo 未用 Redis）。**V2 的 Async Worker 有 MySQL advisory lock（單 worker 防雙上鏈），但未用 Redis 做 distributed lock。**

**Follow-up：** 「`.exists()` + `IntegrityError` 的雙重意義？」「為什麼不 `get_or_create`？（會吞掉 custom 409 邏輯）」「`TransactionTestCase` vs `TestCase`？（前者不 wrap atomic，才測得到真 atomic）」「若 IOTA retry 與 DB 同時重試會雙上鏈？（無 idempotency key → [PLANNED] gap；V2 有 advisory lock 防同 worker 雙上鏈）」「20 併發要怎麼擴到 200？（DB 仍是單一仲裁，會 OK；IOTA 已移至 worker 不阻 HTTP path）」。

---

## 12. IOTA / Blockchain Deep Dive（Flow F）

**On-chain（`firmware_module.move`）：**
- `FirmwareMetadata has key, store`（UID + 各欄位）；`FirmwareEvent has copy, drop`（不含 UID，可 emit）。
- `public entry fun publish(...9 params..., ctx)`：`object::new(ctx)` 建 UID → `transfer::public_transfer(metadata, ctx.sender())` 存到 sender 帳戶 → `event::emit(evt)` 通知。
- Move.toml：`firmware_notify = "0x0"`（IOTA 重訂正後必須 0x0）；`Iota` 框架 git dep。

**Off-chain submit（`submit_firmware.ts`）：**
- `@iota/iota-sdk`：`IotaClient({url: getFullnodeUrl(NETWORK)})`；`Secp256k1Keypair`。
- 取 `getOwnedObjects` + `getObject(showContent)` 找 gas coin（`balance > 1_000_000`）→ `signAndExecuteTransaction`。
- 每個 RPC 包 `withTimeout`（`IOTA_TIMEOUT_MS=30s`）。
- 成功印 `OBJECT_ID:...`（Python `re.search(r"OBJECT_ID:([a-zA-Z0-9x]+)")` 抽出）。
- 以 `npx tsx submit_firmware.ts <9 args>` subprocess 呼叫（`upload_to_blockchain`）。

**Why 上鏈只存 metadata 不存 firmware？** → 鏈上存「metadata + 簽章」作 tamper-evidence anchor；firmware 本體走 mTLS 下載（`customer_request.py`），鏈上只當「事件通知 + 證明存在」。

**Risk / Limitation：**
- IOTA testnet 慢（k6 notes：~2.35s）；`getOwnedObjects` + `getObject` 對每個 object 都 RPC（O(n) RPC）→ 物件多會慢。
- gas coin 篩選「`balance > 1_000_000`」寫死 → 餘額變動會失靈。
- 無「冪等」：重試同一次上鏈會產生多個 object（[PLANNED] gap，無 outbox / dedupe key）。

**Follow-up：** 「IOTA vs 傳統 L1（gas / object model）？」「Move 與 Solidity 語言差異（resource / capability / 不能亂 drop）？」「為什麼 `has key, store` vs `has copy, drop`？」「`ctx.sender()` 誰？（上鏈 keypair 對應地址）」「testnet → mainnet 要改什麼？（network / package id / key / gas）」「subprocess vs 直接 import SDK？（Python↔TS 邊界、npx 依賴）」。

---

## 13. Docker Deep Dive（Flow G 前半）

**Evidence（3 root Dockerfiles + frontend Dockerfiles + compose）：**
- `Dockerfile.customer-agent`：`python:3.10-slim` + `gcc default-libmysqlclient-dev pkg-config`（編 mysqlclient）→ `pip install -r requirements.txt` → COPY `shared/` + `customer_agent/` → `EXPOSE 5000 5001` → `CMD python run_customer_agent.py`。**不 COPY `.env`**。
- `Dockerfile.manufacturer-agent`：同 slim + 裝 **Node 20**（`nodesource setup_20.x`）→ `npm install`（IOTA SDK）→ `EXPOSE 8000`。
- `Dockerfile.manufacturer-client`：slim + mariadb dev → `EXPOSE 5002` → `CMD python manufacturer_client/service.py`。
- frontend Dockerfiles：build Vite `dist`。

**Compose（`docker-compose.yml`）：**
- 5 services：customer-agent、manufacturer-agent、manufacturer-client、nginx、mariadb。
- mariadb **不對 host 暴露**（學術 demo）；`--default-authentication-plugin=mysql_native_password`；`./docker/initdb` → `/docker-entrypoint-initdb.d`；named volume `mariadb_data`。
- 憑證以 volume 掛 `.pem`；`CERT_DIR` env 重映射。
- manufacturer-agent **不對 host 暴露 port**（只經 nginx mTLS 8443 可達）。

**Why：** 「最小 trust 面」——backend 不上 host port，一律經 Nginx；mariadb 不暴露；憑證掛 volume 不進 image。

**Limitation：** `:local` tag + `IfNotPresent`（K8s 端）；image 未做 multi-stage 壓縮（node 層可拆）；`CERT_DIR` 預設路徑仍指向 host 目錄。

**Follow-up：** 「為什麼 image tag 用 `:local` 而非 `:sha`？」「multi-stage 可以把 node build 層分出來？」「`mysql_native_password` 為何？（mysqlclient 支援；`caching_sha2_password` 需 TLS）」「如何縮 image？（squash / slim base / 拆 node 層）」「如何把憑證從 image 移除？（已用 volume，但預設 path 仍存在）」。

---

## 14. Nginx Deep Dive

**Topology（證據 `nginx.conf` + `conf.d/*`）：**
- `events { worker_connections 1024; }`；`http { include conf.d/*.conf; }`。
- `conf.d/customer.conf`：`listen 80`（301 → 443）；`listen 443 ssl`（server-only TLS）：
  - `ssl_certificate /etc/nginx/certs/customer_server_cert.pem`；`client_max_body_size 20M`
  - `root /usr/share/nginx/html; try_files $uri $uri/ /index.html;`（SPA）
  - `location /api/ { proxy_pass https://customer-agent:5001; proxy_ssl_verify off; }`
- `conf.d/manufacturer.conf`：`listen 8443 ssl`（**mTLS**）：
  - `ssl_client_certificate /etc/nginx/certs/client_ca.pem; ssl_verify_client on;`
  - `location /manufacturer/agent/ { proxy_pass http://manufacturer-agent:8000/; }`
  - `location /manufacturer/client/ { proxy_pass http://manufacturer-client:5002/internal/; }`

**Why 拆 conf.d：** nginx 標準慣例；`include` 讓「一份 master config + 多 server block」可獨立維護 / git diff。

**Limitation：** `proxy_ssl_verify off`（自簽）；無 rate-limiting / WAF；`worker_connections 1024` 未依 `worker_processes` 調；無 `gzip` / cache 對 static 的細調。

**Follow-up：** 「`ssl_verify_client on` 在哪做（handshake）？」「為什麼 customer 443 是 server-only 而 8443 是 mTLS？」「`proxy_ssl_verify off` 風險？」「`try_files` 為何必要（SPA 路由）？」「Nginx 在 K8s 是 sidecar 還是獨立 deployment？（`k8s_v2/deployments/nginx.yaml`：獨立 deployment + 2 frontend sidecar `emptyDir`）」。

---

## 15. Kubernetes Deep Dive（Flow G 後半）

**Evidence（`k8s_v2/`，12 YAML；subagent 全讀）：**

| 物件 | 關鍵值 |
|---|---|
| `namespace.yaml` | `thesis`（與 V1 共用） |
| `pvc/customer-db-pvc.yaml` | `thesis-customer-mariadb-data`，RWOnce，100Mi |
| `pvc/manufacturer-db-pvc.yaml` | `thesis-manufacturer-mariadb-data`，RWOnce，100Mi |
| `configmaps/v2-seed-scripts.yaml` | 內嵌 2 個 Python seed（`run_manufacturer_seed.py` + `run_customer_seed.py`）；customer 固定 `3e01e6a7-...` |
| `deployments/customer-agent.yaml` | image `thesis/customer-agent:local`，replicas 2（baseline 可 scale 至 3）, port 5001/5000，`cpu:250m/memory:128Mi` req + `cpu:250m/memory:256Mi` limit（HPA baseline 已補上 [IMPLEMENTED]），readiness/liveness `tcpSocket`，certs volume |
| `deployments/manufacturer-agent.yaml` | `:8000`，同 resources [IMPLEMENTED]，`DJANGO_DEBUG="False"` [VERIFIED 2026-10-07]，secrets：`DJANGO_SECRET_KEY` + `IOTA_PRIVATE_KEY_BASE64` |
| `deployments/manufacturer-client.yaml` | `:5002`，同 resources [IMPLEMENTED]，`UPLOAD_URL/HISTORY_URL` → `https://nginx:8443/...` |
| `deployments/customer-mariadb.yaml` | `mariadb:11`，replicas 1，Recreate，`requests memory 256Mi`（無 limits），readiness `mariadb-admin ping`，掛 PVC |
| `deployments/manufacturer-mariadb.yaml` | 同 customer-mariadb |
| `deployments/nginx.yaml` | `nginx:1.27-alpine` + 2 frontend sidecar（`emptyDir` 複製 dist），port 80/443/8443，讀iness/liveness `tcpSocket` |
| `hpa/hpa.yaml` | 3 支 HPA：`minReplicas 3 / maxReplicas 4`，CPU `averageUtilization 75` |
| `metrics-server.yaml`（kube-system） | [IMPLEMENTED]：metrics-server deployment + service + RBAC + APIService；`kubectl top nodes` / `kubectl top pods` 2026-10-01 [VERIFIED] 返回實際 CPU/mem |
| `jobs/v2-db-seed.yaml` | `backoffLimit 4`，2 initContainers 等兩個 mariadb `ping`，`python:3.10-slim` + `pip install pymysql` 跑 2 seed |

**Critical facts（誠信點，依 2026-10-01 實際狀態更新）：**
- [IMPLEMENTED][VERIFIED] **metrics-server 已部署並可提供 Resource Metrics**（`kubectl top nodes` / `kubectl top pods -n thesis` 有實際數值；`v2/results/hpa/top_nodes_baseline.txt` 存證）。
- [IMPLEMENTED][VERIFIED] **backend Deployment 已加入 CPU/Memory requests**（3 支 deployment cluster spec 確認 `cpu:250m / memory:128Mi` req + `cpu:250m / memory:256Mi` limit；`v2/results/hpa/baseline_3pods.txt` 存證）。
- [IMPLEMENTED][VERIFIED] **HPA 已能取得實際 CPU utilization**（3 支 HPA `TARGETS` 欄有真實 % 值如 `cpu: 16%/75%`，無 `unknown`；`ScalingActive=True / ValidMetricFound`；`v2/results/hpa/hpa_3pods.txt` 存證）。
- [IMPLEMENTED][VERIFIED] **3 replicas baseline 已建立且穩定 Running**（3 backend 各 3/3，node CPU alloc ~75%，無 Pending Pods）。
- [IMPLEMENTED][VERIFIED] **HPA dynamic scale-up 1→2 與 2→3 已實際觀察到**（2026-10-07，k6 50 VU / 3m；hpa-scaling-events.txt 存證：`New size: 2` 5m18s ago / `New size: 3` 3m16s ago；3/3 pod Running，mTLS 10/10 PASS）。scale-up 3→4 未驗證（需更高負載 / 多節點環境）。
- `k8s-manifest-validate`（CI）已擴展至 `k8s_v2/`（含 metrics-server manifests）[VERIFIED 2026-10-07]。
- V1 的 `mariadb` Pod 在集群上仍未刪（V2 用 `customer-mariadb` / `manufacturer-mariadb` 取代）。

**Follow-up：** 「HPA 沒 metrics-server 會怎樣？（`Invalid` / 不動作）」「為什麼 2 PVC + RWOnce？（DB 不能 multi-replica 同掛）」「`resources` 全缺會怎樣？（K8s 1.26+ 會設 default limits，仍建議明寫）」「`DJANGO_DEBUG="False"` 在 prod 的好處？（不洩漏 stack trace，HTTP error 只回 code+message）」「`IfNotPresent` + `:local` 在真集群？（會拉不到 → 要 GHCR）」「為什麼 frontend 用 sidecar + emptyDir 而非 ConfigMap？（dist 太大）」「`tcpSocket` vs `httpGet` probe？（backend 有 `/api/health`，但用 tcp 較簡單）」。

---

## 16. CI/CD Deep Dive（Flow H）

**Evidence（4 workflows；subagent 全讀）：**

| Workflow | Triggers | 重點 |
|---|---|---|
| `test.yml` | push/PR → main, dispatch | 8 jobs：customer-agent-tests、manufacturer-client-tests、manufacturer-agent-tests（mariadb:11 service）、customer-frontend、manufacturer-frontend、nginx-validate、docker-build-push（needs 前 6，GHCR，SHA + latest，**只有 main push 才 push**）、k8s-manifest-validate（已擴展至 `k8s_v2/` [VERIFIED 2026-10-07]） |
| `docker-e2e.yml` | dispatch, PR → main | `workflow_dispatch` 跑 compose e2e + mTLS smoke（curl 8443 用 ecdsa client cert），artifact 存 logs |
| `performance.yml` | **僅 `workflow_dispatch`** | 裝 k6 v2.2.0，10 VU smoke + 50 VU load，artifact 存 jsonl/summary；**soak / 100/200 VU 不在 PR 流程**，須手動觸發 |
| `copilot-setup-steps.yml` | 僅 `.github/workflows/copilot-setup-steps.yml` 路徑變動 | 裝 `@fission-ai/openspec`（Copilot coding agent 用） |

**Why：** test→build→e2e→perf 分層；GHCR 用 `GITHUB_TOKEN`（no extra secret）；SHA tag 可重放；「main push 才 push」省非 PR build 的 push；soak 僅限手動避免污染 PR CI。

**Limitation：**
- e2e 用「產生 CI `.env`」`CI_DB_PASSWORD`；IOTA private key **留空**（不上鏈，避免 CI 觸 testnet）。
- performance 只 10/50 VU，**100/200 與 30-min soak 不在 PR 流程**（手動 `workflow_dispatch`）。
- `copilot-setup-steps.yml` 是 untracked（未 commit）。

**Follow-up：** 「為什麼 GHCR 而非 Docker Hub？（free + token）」「SHA tag 好處？（可重現 / 不漂移）」「nginx `nginx -t` 怎麼驗？（`docker run nginx:1.27-alpine nginx -t`）」「mTLS smoke 在 CI 怎麼做？（compose 內起 nginx 8443 + curl `--cert/--key/--cacert`）」「若 IOTA 上鏈要進 CI？（需要 testnet key + gas，成本高 → 目前跳過）」「為什麼 soak 不在 PR？（耗時 + 資源，只放 workflow_dispatch）」。

---

## 17. React / TypeScript Deep Dive（Flow I）

**Evidence（兩支 app；subagent 全讀 + 我讀 customer/src）：**
- 版本：React `^19.2.8`、Vite `^8.3.0`、Vitest `^5.0.1`、TS `~6.0.2`、jsdom、@testing-library/react。
- **無 axios、無 IOTA JS SDK**：HTTP 一律**原生 `fetch`**；IOTA 只用 `buildIotaObjectUrl` 生成 explorer 超連結（`https://explorer.iota.org/object/{id}?network=testnet`）。
- **Customer app（`App.tsx`）：** `useEffect` + `window.setInterval(10_000)` **10s polling**；`firmwareRequestInFlight` ref 防並行；devices 失敗只標 `devicesUnavailable` 不擋 firmware；`Vite proxy /api → https://localhost:5001`（`secure:false`）。
  - 元件：`Dashboard` / `DeviceList` / `UpdateStatus` / `FirmwareHistory` / `FirmwareList`。
  - `lib/firmware.ts` 純函式：`findLatestByReleaseDate`、`isCurrent`、`countNonCurrent`、`sortFirmwareByReleaseDateDesc`、`computeFirmwareStatus`。**明確註解：「NEVER uses firmware_version for ordering」**（version 名可不合 semver，用 NTP `release_date` 排序）。
- **Manufacturer app（`App.tsx`）：** 表單 state（version / deviceType=esp32 / file / status）；`FormData` POST `/internal/manufacturer/upload`；成功 `dispatchEvent('firmware-history-updated')` 觸發 `FirmwareHistory` 重取（**事件驅動，無 poll**）。`FirmwareHistory` 分頁（`/internal/manufacturer/history/?page=`）。
- `tsconfig.app.json`：`target es2023`、`jsx react-jsx`、`verbatimModuleSyntax`、`erasableSyntaxOnly`；**exclude `*.test.ts(x)`**。

**Why：** 邊緣 / 學術 demo 用 `fetch` 就夠（少 dep）；「version 不參與排序」是刻意（semver 不保證，用時間戳唯一排序）。

**Limitation：**
- 10s polling vs websocket / SSE（無）；`secure:false`（自簽）；`CUSTOMER_ID` 寫死在 `src/api.ts`。
- `FirmwareHistory` 靠 DOM 自訂 event（非 context / store）。

**Follow-up：** 「為什麼 polling 10s 而非 SSE？（simple；後端無 SSE 端點）」「`useRef` 防並行請求的原理？」「React 19 的 `useEffect` cleanup？」「Vite `proxy` 在 prod 怎麼辦？（Nginx `location /api/`）」「`verbatimModuleSyntax` 限制 import 寫法？」「為什麼不用 TypeScript 做 API 型別 from OpenAPI？（無）」。

---

## 18. Frontend Testing Deep Dive

**Evidence：**
- Customer 10 支 test：`lib/firmware.test.ts`（含「anti-intuitive version names（'999' 不等於更新）」與「same version 不同 release_date」）、`iota.test.ts`（`buildIotaObjectUrl` 必 HTTPS + testnet only，**不得出現 mainnet**）、5 支 component test、`App.test.tsx`（mock `global.fetch`：devices 404 不擋 firmware、firmware 500 顯示 Load Error、10s polling）、`App.firmwareSync.test.tsx`、`App.firmwareHistory.test.tsx`。
- Manufacturer 4 支：`App.test.tsx`（mock fetch + 三子元件）、`FirmwareUpload/UploadStatus/FirmwareHistory.test.tsx`。
- `vitest.config.ts`：`environment jsdom` + `globals:true` + 自訂 `<div id="root">` html；`test-setup.ts`：`@testing-library/jest-dom/vitest` + `afterEach(cleanup)`。

**Why mock `global.fetch`：** 前端不連真 server；只驗「UI 對 API 回值的反應」（2xx / 4xx / 5xx / 網路錯誤 的 rendering）。

**Follow-up：** 「React Testing Library 測什麼（user 行為 vs 實作細節）？」「為什麼 `testEnvironmentOptions.html` 自訂 root？」「`vitest globals:true` 的利弊？」「component test 怎麼隔離 IOTA 連結（純字串，不需 mock）？」「為什麼 `firmware.test.ts` 專門測 '999'？（防開發者誤用 version 排序）」。

---

## 19. Backend Testing Deep Dive

**Evidence（2026-10-07 驗證）：**
- `customer_agent/tests/`：`test_apply` / `test_db` / `test_mtls_config` / `test_query_pipeline` / `test_query_pure` / `test_telegram_notify` / `test_verify` / `test_webhook` + `conftest`（mTLS 6 tests 前次 session [VERIFIED]）。
- `manufacturer_client/tests/`：`conftest` + `test_server`（25 tests [VERIFIED]）。
- `transfer_firmware/tests.py`：21 tests，**19 pass / 2 pre-existing fail**（`DownloadFirmwareAPITestCase::test_firmware_download_request_success` + `::test_missing_manufacturer_id` → `Customer.manufacturer.RelatedObjectDoesNotExist`；FK 在 HEAD~1 已存在，**非 V2 regression**）。
- `upload_firmware/tests_concurrency.py`：`TransactionTestCase`，讀**真 ECDSA key/cert**（`ecdsa_manufacturer_*`，commit `3f4bfe5` 既有）；需 `DB_PASSWORD` env（已移除 hardcode，改為 `RuntimeError` guard）。
- `upload_firmware/tests_worker.py`：14 tests，涵蓋 `IotaSubmissionWorker` 狀態管理、placeholder→real object_id 轉換、error sentinel 處理 [VERIFIED 2026-10-07]。
- `upload_firmware/tests_e2e.py`：3 pass + 1 skipped（`test_testnet_smoke` 需 `E2E_TESTNET=1` 環境變數才執行）[VERIFIED 2026-10-07]。
- CI：`manage.py test -v 2`（mariadb service）+ pytest（customer_agent / manufacturer_client）；`upload_firmware` 全部測試在 `test.yml` 中執行。

**Why `TransactionTestCase`：** 併發測試要測**真 atomic / flush**，普通 `TestCase` 會 wrap 在 atomic 內看不到 rollback 行為。

**Why `tests_worker.py` 獨立：** worker 邏輯（`process_iota_submissions`）有獨立的 sentinel state machine（pending → success/failed），需要專門測試 placeholder 轉換、retry、error handling。

**Follow-up：** 「`TransactionTestCase` vs `TestCase` 差異？」「為何 2 支 fail 是 pre-existing 而非 V2？（git log 該 FK 存在於 V2 前）」「concurrency test 用真 cert 有何風險？（金鑰進 repo，學術 demo）」「mTLS test 怎麼不靠真 server？（`ssl` context 驗證 + mock）」「pytest vs Django test runner 混用？」「worker test 如何 mock IOTA submission？（mock `run_blocking_task` + sentinel 狀態驗證）」。

---

## 20. Performance / k6 Deep Dive

**Evidence（`load-test.js` + results）：**
- 測 2 個唯讀 API：`GET /api/customer/<id>/firmware` + `GET /api/customer/<id>/devices`；`tls.insecureSkipTLSVerify`（自簽）；`timeout 10s`；無 sleep（全速）。
- **thresholds（L143–L152）：** `http_req_failed{firmware/devices} rate<0.05`；`firmware_api_errors count==0`；`devices_api_errors count==0`。
- 自訂 `Trend`（`firmware_api_duration` / `devices_api_duration`）+ `Counter`（error / 404）。

### 20.1 Manufacturer Agent 效能演進（V2 重點）

**核心問題：IOTA 上鏈 ~52s 同步阻塞**

原始架構：
```
Client POST
  → Nginx mTLS
  → Gunicorn single worker
  → Django view
  → DB write
  → subprocess (TypeScript IOTA SDK)
  → IOTA network (~52s)
  → HTTP Response
```

每個 upload request 必須**同步等待** IOTA 上鏈完成，IOTA ~52s，導致 worker 被長時間佔用。

**效能數據（100 VU history read path）：**

| Stage | Architecture | RPS | p50 | p95 | p99 | Failure | Evidence |
|---|---|---|---|---|---|---|---|
| Before | Werkzeug single worker + sync IOTA | 14.79 | 5,478ms | 13,580ms | 15,762ms | 0% | `thesis/load_tests/results/v2/manufacturer-before-vu100.out` |
| Phase 1 | Gunicorn 2 workers | 31.29 | 2,750ms | 6,801ms | 8,930ms | 0% | `thesis/load_tests/results/v2/manufacturer-after-phase1-vu100.out` |
| Phase 2 | Async IOTA Worker | 21.15 | 3,883ms | 9,011ms | 11,219ms | ~0.04% | `thesis/load_tests/results/v2/manufacturer-after-phase2-vu100.out` |
| **Latest** | **Final V2 (DEBUG=False)** | **25.33** | **1,555ms** | **5,266ms** | **8,913ms** | **0%** | `latest/soak/soak-50vu-30m.txt` |

**Phase 2 短測數據：**

| VU | RPS | p50 | p95 | p99 | Failure |
|---|---|---|---|---|---|
| 10 | 18.83 | 417ms | 1,165ms | 1,867ms | 0% |
| 50 | 22.60 | 1,678ms | 5,318ms | 12,144ms | 0% |
| 100 | 21.15 | 3,883ms | 9,011ms | 11,219ms | ~0.04% |

**關鍵解讀：**
- Phase 1（Gunicorn 2 workers）RPS 最高（31.29），但 IOTA 仍然同步阻塞，worker 被佔用。
- Phase 2 把 IOTA 從 HTTP lifecycle 移除，RPS 略降（21.15）但 **p95 大幅改善**，因為 request 不再等待 52s IOTA。
- **Latest soak（0% 失敗）**：45,664 requests / 30min / 50 VU，在 350m CPU limit 實驗還原至 250m 後執行。

**Real async upload 對比（面試重點）：**
```
Before（sync IOTA）:
  Client → 等待 ~52s IOTA → Response（~4.2s HTTP + ~52s IOTA）

After（async IOTA Worker）:
  Client → ~4.2s → HTTP 202 Accepted
  Background Worker → ~52s → IOTA completed → DB success
```

**歷史 0.33% soak（Phase 2）：**
- 30,705 requests / 0.33% failure（10×5xx + 92 timeout）
- Evidence：`thesis/load_tests/results/v2/manufacturer-after-phase2-soak30.out`
- 保留作為歷史證據，**不可與本次 0% 直接比較**（執行條件不同）

### 20.2 V1 vs V2 soak（customer-agent，30min, 50 VU）

| Metric | V1（`results/v1/k6_soak30.json`） | V2（`results/v2/k6_soak30.json`） |
|---|---|---|
| total http_reqs | 17,934 | 16,412 |
| firmware fail rate | 0.546%（value `0.00546`） | **20.6%** |
| devices fail rate | 1.24%（value `0.0124`） | **21.6%** |
| overall fail | ~0.89%（threshold 更嚴） | **21.1%（threshold_crossed=true, result=FAILED）** |
| firmware p95 | 7,767 ms | 233 ms |
| firmware p90 | 7,072 ms | — |

> 注意：此表為 **customer-agent** 的 V1 vs V2 數據，與上方 manufacturer agent 效能演進（§20.1）是**不同 service**，不要混淆。

**Critical 誠信點（要主動講）：**
- V1 的 `p95 7767ms`（極高）是「平均長尾」，但 fail rate 只有 0.89%；V2 fail rate 21.1% 但 p95 只有 233ms → **V2 是「大量 timeout」而非「慢回應」**（k6 把 timeout 算 fail）。
- 根因**未完全隔離**：notes 寫「GIL contention（`run_periodic_query` 每 3s 對外 IOTA）＋ Docker Desktop port-forward 累積 TIME_WAIT ＋ IOTA testnet 慢 ~2.35s」，三者都是「可能因素」，**未做逐因素 A/B**。

**Follow-up：** 「fail rate 怎麼算（`http_req_failed` count / total）？」「p95 低但 fail 高代表什麼？（timeout 在 10s threshold 被 cut，慢的不是 latency 而是『未回傳』）」「怎麼隔離 GIL vs port-forward vs IOTA？（分次只變一個：關閉 periodic query / 用 host network / mock IOTA）」「threshold `count==0` 太嚴嗎？（對唯讀 seed API 合理）」「k6 `vus` vs `ramping-vus`？」「soak 30min 對『連線洩漏』夠不夠？（要看 TIME_WAIT 曲線）」。

---

## 21. V1 vs V2（差異對照）

| 面向 | V1 | V2 | 證據 |
|---|---|---|---|
| DB 唯一約束 | `firmware_version` 單欄位 `unique=True`（transfer） | composite `unique_together (manufacturer_id, device_type, firmware_version)` | `transfer_firmware/models.py` vs `upload_firmware/models.py` |
| 併發上傳 | 無明確 409 | `transaction.atomic()` + `IntegrityError` → **409** | `views.py` L580–640 |
| IOTA 上鏈 | 同步 subprocess（HTTP 等待 ~52s） | **Async IOTA Worker**（202 Accepted + 獨立 worker 處理） | `k8s_v2/deployments/manufacturer-iota-worker.yaml`、`upload_firmware/tests_e2e.py` |
| K8s | `k8s/`（V1，`mariadb` Pod） | `k8s_v2/`（12+ YAML，2 獨立 mariadb，HPA，seed Job，metrics-server，IOTA worker） | `k8s/` vs `k8s_v2/` |
| customer DB | 共用 `mariadb` | `customer-mariadb` + `manufacturer-mariadb`（各自 PVC） | `k8s_v2/deployments/*-mariadb.yaml` |
| k6 | results/v1 | results/latest（soak 0% failure）+ results/v2 | `load_tests/results/` |
| CI/CD | `k8s-manifest-validate` 只校驗 V1 | `k8s-manifest-validate` 涵蓋 V2 全目錄 [IMPLEMENTED] | `.github/workflows/test.yml` |
| `DJANGO_DEBUG` | `"True"`（K8s manifest） | `"False"` [IMPLEMENTED][VERIFIED] | `k8s_v2/deployments/manufacturer-agent.yaml` |

**Why V2：** 修正「同版本號跨 manufacturer 誤判 duplicate」→ 改 composite key；加併發 409；**IOTA 改為 async worker（202 語意）**；部署改 K8s V2；CI 校驗 V2；`DEBUG=False`。

**Limitation：** 單節點 Docker Desktop K8s；metrics-server 間歇性 scrape timeout；歷史 0.33% soak 與本次 0% soak 不可直接比較。

---

## 22. Failure Scenarios（主動列「會怎麼壞 + 我的診斷」）

1. **IOTA testnet 慢 / 不通** → `upload_to_blockchain` bounded retry 用盡 → 500（DB 已寫）→ 需手動重試。診斷：看 `[上鏈超時]` log。
2. **DB 唯一約束 hit** → 409（正確語意）；20 併發 1 成功 19 409。
3. **release_date 超出 now+10s** → 3012 拒絕（NTP 未同步）。
4. **簽章錯 / 憑證不匹配** → `verify_signature` False → 1012/2012。
5. **mTLS 客戶端無 cert / 不符 CA** → Nginx `ssl_verify_client on` 拒（503 / 400 handshake fail）。
6. **k6 高併發** → customer-agent single-threaded + periodic query GIL 競爭 → timeout（fail 21.1%）。
7. **gas coin 餘額 < 1_000_000** → submit 拋「沒有足夠餘額」→ 上鏈失敗。
8. **`DJANGO_DEBUG`（K8s）**：已由 `"True"` 改為 `"False"` [IMPLEMENTED]（2026-10-07 session），mTLS smoke 驗證通過。
9. **`CUSTOMER_ID` 寫死** → 換 customer 前端無資料（seed 固定 UUID）。
10. **PVC 100Mi 不夠** → LONGBLOB 多版本 DB 滿 → 上線失敗。
11. **`IfNotPresent` + `:local`** → 真集群 pull 不到 image。
12. **V1 mariadb Pod 未刪** → 雙 DB 來源混淆。
13. **metrics-server 間歇性 scrape timeout**：kubelet 10s scrape timeout 導致 `FailedGetResourceMetric`，HPA 在 metrics 可讀時正常觸發 rescale（1→2→3 已觀察到 [VERIFIED]）；**Metrics Server = CONDITIONAL**，非完全 PASS。
14. **`proxy_ssl_verify off`** → customer 上游未驗證（MITM 風險，自簽容忍）。

---

## 23. Scalability Analysis

- **水平：** manufacturer-agent replicas=3（K8s，HPA min=3/max=4，CPU 75%）[IMPLEMENTED][VERIFIED]。HPA 1→2→3 已實際觀察到 [VERIFIED]。
- **IOTA 是硬瓶頸：** `getOwnedObjects` + 每 object `getObject`（O(n) RPC）+ testnet 慢 → 上鏈 throughput 受限。**V2 已改為 async worker**，不再阻塞 HTTP request。
- **DB investigation：** `Max_used_connections = 18/151`、`Slow_queries = 0`；根因為**單節點 CPU 飽和**（非 DB connection pool）；350m CPU limit 實驗使失敗率惡化至 8.01%（已還原至 250m）。**DB = CONDITIONAL**。
- **customer_agent：** single-threaded + 無 pool → **不適合高 QPS**；要 scale 需 Gunicorn 多 worker + DB pool + 把 periodic query 拆出。
- **Nginx：** `worker_connections 1024` 可調；static 可加 cache。
- **前端：** polling 10s × N 使用者 → API QPS = N/10；要降負載改 SSE / websocket / ETag。
- **DB pool / Redis / Kafka：** **repo 未使用**（[GENERAL]，不要吹）。可提「未來可加」但別說「已實作」。

**Follow-up：** 「怎麼讓 customer_agent 撐 10× QPS？（worker × DB pool × 拆 periodic query）」「IOTA 怎麼改 throughput？（batch / 只 event 不 getObject / 本地 cache object）」「DB 怎麼水平？（read replica / 分庫 by manufacturer_id）」。

---

## 24. Security Analysis

**Strengths（證據）：**
- 簽章全鏈：metadata + firmware 雙簽章；響應簽章（`ManufacturerAgentSignature`）可被 client 驗。
- mTLS 雙向（nginx 8443 + customer device 5000）[IMPLEMENTED][VERIFIED]。
- DB 參數化（pymysql `%s` + Django ORM）防 SQL 注入。
- 409 + atomic 防併發 duplicate。
- CI 不上鏈（IOTA key 留空）。
- `DJANGO_DEBUG="False"` [IMPLEMENTED]（2026-10-07 session 修正，mTLS smoke 驗證通過）。

**Weaknesses / risks：**
- git-tracked 自簽 cert（學術 demo；正式要 CA 簽 + 輪換）。
- `proxy_ssl_verify off`（customer upstream）。
- `CUSTOMER_ID` 硬編前端。
- 無 rate-limit / WAF / auth token（API 靠 mTLS 而非 token）。
- 無 secrets 管理（`DJANGO_SECRET_KEY` / `IOTA_PRIVATE_KEY_BASE64` 以 K8s secret，但 `.env` 在本機含密碼，[UNTRACKED] 未 commit）。
- 無 audit log（只有 `print`）。

**Follow-up：** 「mTLS vs token auth？（裝置端無 browser 情境，mTLS 適合）」「如何輪換 cert？（K8s secret + CA 重簽 + 重啟）」「如何 audit？（structured log + 上鏈 event 天然 audit）」「SQL 注入如何防（參數化 + ORM）」。

---

## 25. Git / Repository Security

**Evidence（前 session 審計）：**
- 移除 `tests_concurrency.py` 的 `os.environ.setdefault('DB_PASSWORD','ap365084')` → 改為 `if os.environ.get('DB_PASSWORD') is None: raise RuntimeError(...)`（不 hardcode）。
- `V2_IMPLEMENTATION_REPORT.md` 無密碼（只有 `127.0.0.1:3306`）。
- 未 commit 的 `.env` 仍含 `ap365084`（[UNTRACKED]，未進 git）。
- ECDSA test key/cert 是 commit `3f4bfe5` 的既有（學術用）。
- push 前 `git diff --cached --check` 過（修 2 行 markdown 行尾空白）；secret scan PASS。

**Follow-up：** 「為何不 rotate 該 password？（任務限制 + 公開 repo，改用 env 注入 + 文件化）」「`.env` 未 track 對嗎？（對，但要在 `.gitignore` + 文件講明）」。

---

## 26. AI Agent / OpenSpec

**Evidence（inventory）：**
- `openspec/`：`config.yaml` + `changes/`（8 個 change：add-customer-agent-tests / add-customer-firmware-get-api / add-customer-firmware-history-status-view / add-customer-frontend / add-manufacturer-client-server-tests / archive / fix-customer-firmware-load-error / improve-customer-firmware-history-responsive-layout）+ `specs/`。
- `.github/{agents,prompts,skills,workflows}`：`copilot-setup-steps.yml` 裝 `@fission-ai/openspec`。
- `.agents/`、`.claude/`、`.cline/`、`.gemini/`、`.qwen/`、`.opencode/`：各 agent 框架的 skill / instruction 目錄。
- Skills（本 session 載入）：`openspec-apply-change` / `archive` / `explore` / `propose` / `sync-specs` / `update-change`。

**How it was used：** 每個 feature 走 OpenSpec propose → design + spec + tasks → implement → archive 流程；用多 agent（copilot / claude / cline / gemini / qwen / opencode）共用 `openspec/` 作為「single source of intent」。

**Follow-up：** 「OpenSpec 的 change / spec / archive 模型？」「多 agent 共用 spec 如何避免衝突？（change 隔離 + tasks checklist）」「skill 如何被 agent 觸發？（frontmatter + 路徑）」。

---

## 27. Interview Knowledge Map（總表）

| 知識領域 | 本專案證據 | 要背的通用概念 |
|---|---|---|
| REST / DRF | `UploadFirmwareAPIView`、`HistoryListAPIView` | dispatch / parser / serializer / pagination |
| 併發 / DB | `transaction.atomic()` + `IntegrityError` + composite unique | race、MVCC、`SELECT FOR UPDATE`、outbox |
| Crypto | ECDSA / RSA 簽章、NTP、Secp256k1 | PKI 鏈、X509、k 隨機、PKCS1v15 vs PSS |
| mTLS | nginx 8443 + customer 5000 | TLS 握手、client cert、CRL/OCSP |
| IOTA / Move | `firmware_module.move` + `submit_firmware.ts` | object model、event、gas、capability |
| Docker | 3 Dockerfile + compose | layer、多 stage、`mysql_native_password`、volume |
| K8s | 12 YAML | Deployment/HPA/PVC/Job/probe/metrics-server |
| Nginx | conf.d + mTLS | worker、`try_files`、`proxy_ssl_verify` |
| CI/CD | 4 workflows | SHA tag、GHCR、service container、artifact |
| React/TS | 兩支 app | polling vs SSE、`useRef` 防並行、RDT |
| 測試 | pytest + Vitest + TransactionTestCase | mock fetch、conftest、thresholds |
| 效能 | k6 v1/v2 | p50/p95、fail rate、GIL、TIME_WAIT |

---

## 28. Interview Follow-up Trees（精選 6 棵）

**Tree A — Upload：** `409 為什麼？` → `併發怎麼擋？` → `IOTA 在事務內嗎？` → `上鏈失敗 DB 已寫怎麼辦？` → `outbox 為何沒做？` → `如何補 reconcile？`
**Tree B — mTLS：** `雙向怎麼確認？` → `chain 怎麼驗？` → `ECDSA vs RSA？` → `Secp256k1 跟 PKI 差異？` → `cert 輪換？`
**Tree C — IOTA：** `只上鏈 metadata 不上 firmware？` → `Move capability？` → `gas coin 怎麼選？` → `重試會雙上鏈？` → `testnet→mainnet？`
**Tree D — K8s：** `metrics-server 如何部署？` → `backend 如何補 250m requests？` → `3-pod baseline 為何需要？` → `HPA 3→4 動態擴縮如何證明？` → `DB 為何單 replica？` → `V1 mariadb 為何還在？` → `How to prod-ready？`
**Tree E — Perf：** `V2 fail 21% 為何 p95 反而低？` → `timeout vs latency？` → `GIL 怎麼佔？` → `如何隔離三因素？` → `soak 看什麼？`
**Tree F — DB：** `composite unique 為何？` → `exists + atomic 雙層？` → `get_or_create 為何不？` → `LONGBLOB 多大？` → `pool 為何無？`

---

## 29. Interview Danger Zones（≥20）

1. 「HPA 真的會縮放嗎？」（**1→2→3 已實際觀察到 [VERIFIED]**：k6 50 VU / 3m 觸發，`SuccessfulRescale New size: 2` 和 `New size: 3` 記錄於 `latest/hpa/hpa-scaling-events.txt`；metrics-server 有間歇性 scrape timeout，**Metrics Server = CONDITIONAL**）
2. 「V2 比 V1 快嗎？」（customer-agent V2 fail rate 上升是 timeout 假象；manufacturer agent V2 async worker 將 IOTA 從 HTTP lifecycle 移除，latest soak 0% failure）
3. 「DB 是 root cause 嗎？」（**不是**：`Max_used_connections=18/151`、`Slow_queries=0`；根因為單節點 CPU 飽和；**DB = CONDITIONAL**）
4. 「IOTA 上鏈失敗會怎樣？」（V2：worker 重試，DB 記錄 failed 狀態；不會影響 HTTP response 因為已 202）
5. 「DB 密碼在哪？」（`.env`，未 commit；tests 用 env guard）
6. 「V1 mariadb 刪了嗎？」（否，cluster 仍 up）
7. `k8s_v2` 有 CI 校驗嗎？（**有**：`k8s-manifest-validate` dry-run 涵蓋 V2 全目錄 [IMPLEMENTED]）
8. `DEBUG` 會上 prod 嗎？（**已修正為 `"False"` [IMPLEMENTED][VERIFIED]**，mTLS smoke 驗證通過）
9. `proxy_ssl_verify off` 風險？（自簽，正式要 on）
10. `CUSTOMER_ID` 為何寫死？（seed 固定 UUID）
11. `IfNotPresent :local` 在集群？（拉不到）
12. 無 Redis/Kafka/pool 怎麼撐負載？（會 GIL + TIME_WAIT，不適合高 QPS）
13. 雙上鏈會發生嗎？（會，無 idempotency key；worker 用 MySQL advisory lock 防重入）
14. `getOwnedObjects` O(n) RPC 會慢嗎？（會）
15. gas coin 篩選寫死 1_000_000？（會失靈）
16. 簽章 payload `|` 拼接會改格式？（全失敗）
17. `ALLOWED_TIME_DRIFT 10s` NTP 不同步會誤拒？（會）
18. `firmware_version` 不用來排序，為什麼？（semver 不保證，用 NTP）
19. 無 audit log？（只有 print）
20. ECDSA test key 進 repo？（學術 demo，正式要抽掉）
21. 無 read replica，DB 壓力？（single MariaDB）
22. 10s polling 太多 client？（QPS=N/10 線性成長）
23. `worker_connections 1024` 沒調？（會瓶頸）
24. `.env` 在 image 嗎？（compose 掛 ro，但未 track）

---

## 30. Missing Knowledge（HIGH / MEDIUM / LOW）

**HIGH（被問到會卡）：**
- IOTA object model / Move capability 精確語意（`copy` vs `drop` 何時可用）
- 怎麼「真正」把 IOTA 重試做成 idempotent（outbox + dedup key）
- 怎麼把 customer_agent 改多 worker + DB pool（Gunicorn + DB pool 實作細節）
- 怎麼做 cert 輪換（CA 重簽 + K8s secret rollout）

**MEDIUM：**
- Nginx `worker_processes` / `connections` 調參
- k6 `ramping-vus` 場景設計
- Read replica / 分庫 by manufacturer
- SSE / websocket 取代 polling
- `mysql_native_password` vs `caching_sha2_password` 全貌

**LOW（概念會但沒用過）：**
- 其他 DBMS（Postgres / Mongo）
- 其他 orchestration（Fargate / 純 VM）
- 其他 L1 / 鏈（Ethereum / Solana）
- Service mesh（Istio mTLS）

---

## 31. Future Improvements（可被問「下一步」）

1. IOTA idempotency：outbox 表 + dedup key + 重試 worker。
2. customer_agent 拆 periodic query 為獨立 worker + Gunicorn 多 worker + DB pool。
3. K8s prod：`resources` 已 250m/128Mi [IMPLEMENTED]、`DEBUG=False` [IMPLEMENTED]、secret rotation、metrics-server scrape timeout 優化（檢查 kubelet 參數或 metrics-server 資源 limit）。
4. 上鏈 event subscribe（非 3s 輪詢）→ 降低 IOTA 呼叫次數。
5. 加 SSE / websocket 取代 10s polling。
6. Read replica + LONGBLOB 分表（metadata 小表 / firmware_data 大表）。
7. 憑證抽離 repo（完全 volume + 不預設 host 路徑）。
8. V1 `mariadb` Pod 清除 + V1/V2 雙 DB 去混淆。
9. 加 structured audit log + 告警。
10. IOTA worker multi-replica（需獨立 idempotency 機制 + evidence 支持）。

---

## 32. Q1–Q217 Coverage Matrix

> 因為 Q1–Q217 是「外部 question bank」，本 repo 能「以實際專案證據回答」的比例有限。
> 以下只標「哪些 Q 可用本專案證據直接回答」vs「僅通用知識」。
> 原則：有 file evidence 才算 [COVERED-BY-PROJECT]；否則 [GENERAL-ONLY]。

**可用專案證據回答（高信心）：**
- 「upload 怎麼做？」「併發怎麼防 duplicate？」「409 何時？」「IOTA 上鏈流程？」「mTLS 怎麼終結？」「Docker/K8s 怎麼部署？」「CI 跑什麼？」「k6 結果？」「V1 vs V2？」「DB schema？」「簽章格式？」→ **對應 §5–§21，全部 [COVERED-BY-PROJECT]**。
- 「測試怎麼寫？」「concurrency test？」「frontend 測什麼？」→ §18–19 [COVERED]。
- 「HPA 真的會縮放嗎？」→ **1→2→3 已觀察到 [VERIFIED]**（`latest/hpa/hpa-scaling-events.txt`），metrics-server 間歇性 scrape timeout 為 CONDITIONAL。
- 「DB 是瓶頸嗎？」→ **不是**（`Max_used_connections=18/151`、`Slow_queries=0`）；根因為單節點 CPU 飽和；350m 實驗惡化（8.01%），已還原至 250m。
- 「V2 soak 結果？」→ **45,664 requests / 0% failure**（`latest/soak/soak-50vu-30m.txt`）。

**只有通用知識（repo 無證據，勿吹）：**
- 「Redis 怎麼用？」「Kafka 怎麼用？」「連線池怎麼調？」「Postgres 怎麼用？」→ [GENERAL-ONLY]。repo 未使用 Redis / Kafka / pool，**不可說「我做了」**。
- 「metrics-server 怎麼裝？」→ 已部署 [IMPLEMENTED][VERIFIED]，HPA 1→2→3 已觀察到 [VERIFIED]；間歇性 scrape timeout 為 CONDITIONAL。

**實務策略：** 任何 Q，先問「這是不是我專案裡做的？」→ 是則引 file / 行為；否則明說「通用知識，我專案未用，但可以怎麼做」。

---

## 33. A1–A15 Coverage Matrix

> A1–A15 為「appendix / 進階題」同樣處理。

- **可用專案證據（[COVERED-BY-PROJECT]）：** A 系列若落在 §5–§24 的 deep dive（upload / 併發 / IOTA / mTLS / K8s / perf / DB / CI / frontend / testing）→ 直接引證據。
- **僅通用知識（[GENERAL-ONLY]）：** 任何「我沒在 repo 實作」的進階題（如「設計一個全球多 region IOTA 同步」「怎麼做跨鏈 bridge」）→ 明說未實作，給設計思路。
- **誠信規則：** 每個 A 答案標 [IMPLEMENTED] / [VERIFIED] / [PLANNED] / [GENERAL]。

---

## 34. Final Interview Preparation Checklist

**要能 60 秒講清楚的：**
- [x] 整條 OTA 鏈（upload → sign → on-chain anchor → customer detect → download → verify）
- [x] 3 service 邊界 + Nginx 雙埠（443 / 8443）
- [x] mTLS 雙終結點（nginx + customer device）
- [x] IOTA 只上鏈 metadata（anchor），firmware 走 mTLS
- [x] 併發：composite unique + atomic + 409
- [x] Docker → K8s V2（12+ YAML）+ CI 4 workflow + GHCR SHA
- [x] **V2 效能演進：Before（sync IOTA）→ Phase 1（Gunicorn 2 workers）→ Phase 2（Async Worker）→ Latest（0% failure）**
- [x] **HPA 1→2→3 已實際觀察到**（k6 50 VU / 3m 觸發）

**要主動坦白的誠信點：**
- [x] metrics-server 有間歇性 kubelet scrape timeout（10s），**Metrics Server = CONDITIONAL**；HPA 在 metrics 可讀時正常觸發
- [x] 執行環境為單節點 Docker Desktop K8s，多節點行為無法驗證
- [x] 歷史 0.33% soak 與本次 0% soak 執行條件不同，**不可直接比較**
- [x] V1 mariadb Pod 未刪
- [x] customer-agent V2 k6 退化（fail rate 上升）根因未完全隔離

**被問到「怎麼做」要能脫口而出的（通用 + 設計）：**
- [x] outbox / idempotency key
- [x] Gunicorn 多 worker + DB pool
- [x] SSE 取代 polling
- [x] cert 輪換 + CA
- [x] metrics-server 安裝 + resources 明寫【**已完成 [IMPLEMENTED]**；`DEBUG=False` 已修正 [IMPLEMENTED]】

**絕對不要說（repo 無證據）：**
- [ ] 「我用 Redis / Kafka / 連線池」
- [ ] 「我做了 IOTA 跨鏈 bridge」
- [ ] 「HPA 完全正常」（**1→2→3 已觀察到 [VERIFIED]；metrics-server 間歇性 scrape timeout 為 CONDITIONAL，不要說完全 PASS**）
- [ ] 「DB 沒有問題」（**DB = CONDITIONAL：找到根因為 CPU 飽和，但單節點環境限制，不可宣稱 DB 完全無問題**）

---

## 35. V2 Optimization Story（面試核心）

> 本章節是面試時最重要的優化敘事，按照「問題 → 證據 → 根因 → 優化 → 前後數據 → 驗證 → 限制」整理。

### 35.1 原始問題（Phase 0）

原始流程：
```
Client
  ↓
Nginx HTTPS / mTLS
  ↓
Werkzeug single worker
  ↓
Django view
  ↓
DB write
  ↓
subprocess (TypeScript IOTA SDK)
  ↓
IOTA network (~52s)
  ↓
HTTP Response
```

**核心問題：** 每個 HTTP request 必須**同步等待** IOTA 上鏈完成（~52s）。
高併發時，worker 被長時間佔用 → 其他 request 排隊 → latency 上升 → 504 / timeout。

### 35.2 發現瓶頸的過程（Measurement → Evidence → Hypothesis）

**Step 1：基線測量（Before）**
- 100 VU / 2m：RPS=14.79，p95=13,580ms
- 觀察：RPS 極低，p95 極高，單一 worker 是 head-of-line blocking

**Step 2：假設 1 — 增加 worker 數量**
- Phase 1：Werkzeug → Gunicorn 2 sync workers（CPU limit=250m，選 2 而非更多是有意的）
- 結果：RPS=31.29（+111%），p95=6,800ms（-50%）
- **限制：** IOTA 仍同步阻塞，worker 仍被 52s 佔用；RPS 提升只來自併發度，不是根本解決

**Step 3：假設 2 — 把 IOTA 從 HTTP lifecycle 移除**
- Phase 2：Async IOTA Worker 架構
- 結果：HTTP 202 在 ~4.2s 回傳，IOTA 由獨立 worker 背景處理（~52s）
- 100 VU：RPS=21.15，p95=9,011ms（read path），failure≈0.04%

**Step 4：DB 調查**
- `Max_used_connections = 18/151`（未接近 pool 上限）
- `Slow_queries = 0`
- 30-min soak：30,705 requests / 0.33% failure（10×5xx + 92 timeout）
- **根因：單節點 CPU 飽和**（node ~91% CPU），非 DB connection pool

**Step 5：350m CPU limit 實驗**
- 將 agent Pod CPU limit 由 250m 提高至 350m
- 結果：failure rate **惡化**至 8.01%
- 原因：node 已飽和，提高 limit 使資源競爭更嚴重
- **還原至 250m**

**Step 6：最終驗證**
- Latest soak：45,664 requests / 0% failure / p50=1,555ms / p95=5,266ms / p99=8,913ms
- HPA 1→2→3 已實際觀察到

### 35.3 Optimization Summary Table

| Optimization | Problem | Solution | Evidence |
|---|---|---|---|
| Worker model | Single-worker blocking | Gunicorn 2 workers | RPS 14.79→31.29, p95 13,580→6,800ms |
| IOTA blocking | ~52s synchronous blockchain operation | Async IOTA Worker (202) | HTTP 202 in ~4.2s, IOTA background ~52s |
| DB investigation | timeout / 5xx under load | Evidence-based investigation | connections 18/151, slow queries 0, root cause = CPU saturation |
| HPA | concurrency scaling | Kubernetes HPA (1→3 demo) | `SuccessfulRescale New size: 2/3` observed |
| Security | unauthorized TLS clients | mTLS (Nginx 8443) | valid cert → 2xx, no cert → 400 |
| Production config | DEBUG enabled in K8s | `DJANGO_DEBUG="False"` | rollout + mTLS smoke verified |

### 35.4 Before / After 效能比較表

| Stage | Architecture | 100 VU RPS | p95 | Failure | Evidence |
|---|---|---|---|---|---|
| Before | Single worker + sync IOTA | 14.79 | 13,580ms | 0% | `thesis/load_tests/results/v2/manufacturer-before-vu100.out` |
| Phase 1 | Gunicorn 2 workers | 31.29 | 6,800ms | 0% | `thesis/load_tests/results/v2/manufacturer-after-phase1-vu100.out` |
| Phase 2 | Async IOTA Worker | 21.15 | 9,011ms | ~0.04% | `thesis/load_tests/results/v2/manufacturer-after-phase2-vu100.out` |
| Latest | Final V2 (DEBUG=False) | 25.33 (50 VU) | 5,266ms | 0% | `latest/soak/soak-50vu-30m.txt` |

> **關鍵解讀：** Phase 1 RPS 最高（31.29）是因為 IOTA 同步阻塞時，read path（History API）不受 IOTA 影響；Phase 2 的價值不在 RPS 數字，而在**把 52s IOTA 從 HTTP lifecycle 移除**。

### 35.5 面試問答（18 題）

**Q1：這個專案在做什麼？**
> IoT 安全韌體更新系統：manufacturer 上傳韌體 → IOTA 上鏈 metadata anchor → customer agent 偵測上鏈事件 → OTA 更新。mTLS 作為信任邊界，Nginx 終結 TLS，Docker 開發、K8s 部署。

**Q2：為什麼需要 Blockchain / IOTA？**
> 韌體完整性需要防竄改的記錄。IOTA 上鏈 metadata（hash、version、release date）作為不可變 anchor， firmware 本身走 mTLS 下載（不上鏈，避免 gas 成本與鏈上空間限制）。

**Q3：原本 architecture 有什麼問題？**
> IOTA 上鏈同步阻塞 HTTP request（~52s），高併發時 worker 被佔用，request 排隊，latency 急升，出現 timeout / 504。

**Q4：你怎麼發現 performance bottleneck？**
> k6 壓測：100 VU 下 RPS=14.79、p95=13.58s，明顯不正常。觀察 request lifecycle 發現每個 request 必須等 IOTA 完成才回傳，IOTA ~52s 是根本原因。

**Q5：為什麼不是先加 DB pool？**
> 先看證據：`Max_used_connections=18/151`（遠未滿）、`Slow_queries=0`。DB 不是瓶頸。瓶頸是 worker 被 IOTA 阻塞，不是 DB。加 DB pool 解決不了問題。

**Q6：為什麼先從 single worker → Gunicorn？**
> 最簡單的優化：Werkzeug `run_simple()` 是單 worker，head-of-line blocking。Gunicorn 2 workers 讓 read path 可以併發處理，RPS 翻倍（14.79→31.29）。這是「先解最淺層問題」的工程決策。

**Q7：為什麼最後改 Async Worker？**
> Gunicorn 解決了 read path 併發，但 write path（upload）仍被 IOTA 52s 阻塞。真正解決是「把 IOTA 從 HTTP lifecycle 移除」：Upload API 回 202 + 寫 pending DB record，獨立 worker 背景處理 IOTA，完成後 update DB。

**Q8：為什麼 HTTP 202？**
> 202 = "Request accepted, processing will continue asynchronously"。語意正確：request 已被接受並完成必要 persistence（firmware + metadata + pending record），但 IOTA 上鏈尚未完成。不是 200（IOTA 未成功），不是 201（不是 resource 建立完成）。

**Q9：IOTA 約 52 秒，怎麼避免 API timeout？**
> 把 IOTA 從 HTTP request lifecycle 移除。API 在 ~4.2s 內回 202，IOTA 由獨立 worker 背景處理。Client 透過 History API 輪詢狀態（pending / success / failed）。

**Q10：DB 有沒有 bottleneck？**
> 調查結果：`Max_used_connections=18/151`（12%）、`Slow_queries=0`。DB 不是瓶頸。根因為單節點 CPU 飽和（~91%）。

**Q11：你怎麼證明 DB 不是主要瓶頸？**
> 三層證據：(1) connection usage 18/151 遠未滿；(2) slow queries = 0；(3) 350m CPU limit 實驗使失敗率惡化（8.01%），證明 node CPU 已飽和，增加 CPU limit 無法解決。結論：DB = CONDITIONAL（不是 root cause，但單節點環境限制）。

**Q12：CPU 250m / 350m 實驗說明什麼？**
> 在單節點環境下，node CPU 已 ~91% 飽和。提高 Pod CPU limit 由 250m→350m 使失敗率由 1.26% 惡化至 8.01%。這是 resource scheduling evidence：調高 limit 不一定改善 throughput，反而可能惡化。

**Q13：HPA 怎麼驗證？**
> k6 50 VU / 3m 負載觸發 HPA：觀察到 `SuccessfulRescale New size: 2`（5m18s ago）和 `New size: 3`（3m16s ago）。3 pod 全部 1/1 Running。證據存檔於 `latest/hpa/`。

**Q14：為什麼 HPA min=3 max=4？**
> min=3 確保 baseline 可用性（3 個 Pod 分散負載）；max=4 是單節點 CPU 限制下的上限（再高會使 node 飽和惡化）。CPU target 75% 是常見 production 設定。

**Q15：為什麼又做 1→2→3 demo？**
> Production profile（min=3/max=4）無法演示 scale-up 因為 baseline 已是 3。Demo profile（min=1/max=3，CPU 50%）可以在單節點環境下演示 1→2→3 的 HPA 觸發行為，證明 HPA 機制正常運作。

**Q16：mTLS 怎麼驗證？**
> k6 Pod（掛載 client cert）→ in-cluster Nginx:8443：10 requests / 0% failure / 全 2xx。無 cert 直接 curl：HTTP 400（Nginx `ssl_verify_client on` 拒絕）。

**Q17：CI/CD 做了什麼？**
> `test.yml`：Django tests（MariaDB service）+ concurrency tests（獨立 schema）+ `makemigrations --check` + client tests + 2× frontend tests/build + `docker compose config` + k8s manifest dry-run。Performance/soak 僅限 `workflow_dispatch`。

**Q18：如果 production 要再改善，你會怎麼做？**
> (1) 多節點 cluster（解決單節點 CPU 飽和）；(2) 讀寫分離（read replica）；(3) IOTA idempotency key（防雙上鏈）；(4) SSE / websocket 取代 polling；(5) metrics-server scrape timeout 優化；(6) structured audit log + 告警；(7) cert 輪換機制。

### 35.6 Engineering Mindset（面試要強調的思考方式）

> 「我沒有看到 timeout 就直接增加 DB pool 或 Redis，而是先確認 connection usage、slow query、CPU、worker behavior，再決定優化方向。」

```
Problem（timeout / 504）
  ↓
Measurement（k6 100 VU：RPS=14.79，p95=13.58s）
  ↓
Evidence（IOTA ~52s 同步阻塞；DB connections 18/151；slow queries 0）
  ↓
Hypothesis（worker blocking，非 DB）
  ↓
Small Experiment（Gunicorn 2 workers：RPS 翻倍）
  ↓
Optimization（Async IOTA Worker：202 + background processing）
  ↓
Regression Test（46 general + 14 worker + 2 concurrency tests）
  ↓
Load Test（30-min soak：45,664 requests / 0% failure）
  ↓
Final Validation（HPA 1→2→3 + mTLS + CI/CD）
```

---

## Appendix — 最終統計

- **Files scanned（this session 直接讀 / 列舉）：** 25+ source files（含 `views.py`、`models.py`、`submit_firmware.ts`、`firmware_module.move`、`Move.toml`、`shared/config.py`、`customer_agent/{config,webhook,customer_request,db,run_customer_agent}.py`、`nginx/nginx.conf` + `conf.d/{customer,manufacturer}.conf`、`load-test.js`、`results/{v1,v2,latest}/`、`k8s_v2/*`、`.github/workflows/*`、兩支 frontend）
- **Major technologies：** Python(Flask/Django), MariaDB, IOTA+Move, ECDSA/RSA mTLS PKI, Nginx, Docker, K8s, GitHub Actions, React19+Vite+TS+Vitest, k6, ESP32, Telegram, OpenSpec/AI agents
- **Flows analyzed：** A–J（10 條，逐行級）
- **Q1–Q217 / A1–A15：** 本 repo 能「以實際證據回答」≈ 專案核心 Q（upload/concurrency/IOTA/mTLS/k8s/CI/perf/frontend/testing），其餘為 [GENERAL-ONLY]（見 §32/§33）
- **Potential follow-up questions：** 8 棵 follow-up tree（§28）+ 各章 Follow-up（共 60+ 條可深挖）+ **18 題 V2 優化故事問答（§35.5）**
- **Danger zones：** 24（§29，已更新至 2026-10-07 驗證狀態）
- **Knowledge gaps：** HIGH 4 / MEDIUM 5 / LOW 4（§30）
- **V2 Optimization Story：** §35（完整「問題→證據→根因→優化→前後數據→驗證→限制」敘事）
- **Final PASS Matrix：** 見 `docs/V2_NEXT_PHASE_REPORT.md` §17
- **Report path：** `INTERVIEW_PROJECT_DEEP_DIVE.md`
