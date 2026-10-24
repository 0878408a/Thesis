# Manufacturer Agent 效能瓶頸調查報告（僅調查，未修改）

> 這是 Phase 1 前的初步調查紀錄，已由 [manufacturer-agent-v2-final-report.md](manufacturer-agent-v2-final-report.md) 取代；請以最終報告中的實作與驗證結果為準。

> 本次僅針對 Manufacturer Agent 做「是否與 Customer Agent 相同的 single-worker / Werkzeug 並行瓶頸」調查，**未做任何代碼或配置改動**（除了一個新的 k6 測試腳本 `thesis/load_tests/manufacturer-history-test.js`，純只讀、不影響生產）。是否採用與 Customer Agent 相同的 Gunicorn 修復，請見 §6 結論後再決定。

## 1. 實際伺服器 / process 確認

| 項目 | 現況 |
|---|---|
| `thesis/manufacturer_agent/run_manufacturer_agent.py` | 使用 `werkzeug.serving.run_simple()`（`from werkzeug.serving import run_simple`），單執行緒、單 worker。 |
| `thesis/manufacturer_agent/core/wsgi.py` | 標準 Django `get_wsgi_application()`，未接 Gunicorn/uWSGI。 |
| `thesis/requirements.txt` | 含 `Django==5.1.6`、`gunicorn==25.1.0`（gunicorn 套件本身已安裝，但 Manufacturer 端**未使用**）。 |
| `Dockerfile.manufacturer-agent` | `CMD ["python", "run_manufacturer_agent.py"]` — 直接以單一 `python` process 啟動 Werkzeug，無 Gunicorn 啟動指令。 |
| k8s Deployment `manufacturer-agent` | `image: thesis/manufacturer-agent:local`、`imagePullPolicy: IfNotPresent`，無 `command`/`args` 覆蓋 → 沿襲 Dockerfile CMD。 |
| **k8s Pod 內實際 process**（`kubectl exec` 讀 `/proc/*/cmdline`） | **只有一個 `python run_manufacturer_agent.py`（PID 1）**，無其他 worker process。已親自在 3 個製造商 pod 上確認。 |
| Nginx upstream | `manufacturer.conf`：`proxy_pass http://manufacturer-agent:8000/`（plain HTTP，mTLS 由 nginx 終端），對接單 worker 的 Django/Werkzeug。 |

**結論**：Manufacturer Agent 目前**仍然是「單 worker Werkzeug run_simple」**，與 Customer Agent 修復前的架構完全相同（Django WSGI → Werkzeug run_simple → 1 worker）。

## 2. 實際 resource limits

`kubectl get deployment manufacturer-agent -n thesis`：

```json
{"limits":{"cpu":"250m","memory":"256Mi"},"requests":{"cpu":"250m","memory":"128Mi"}}
```

- 與 `customer-agent`（修復前）的 limits **完全相同**（cpu=250m / memory=256Mi）。
- cgroup `cpu.max` = `25000 100000`（同 customer-agent 修復前）。
- `cpu.stat`：`nr_throttled=574`（低，代表製造商側負載低，未觸發大量 throttling；與 customer-agent 修復前的 `nr_throttled=12051` 相比，主要是因為目前製造商端沒有持續負載測試在跑）。
- 記憶體 `memory.max`=256Mi，`memory.current`~80Mi。

## 3. Manufacturer Agent API 表面分析

`thesis/manufacturer_agent/core/urls.py` + 各 app urls：

| API | 路徑 | 型別 | 負載特徵 |
|---|---|---|---|
| Firmware upload | `POST /upload_firmware/upload/` | 長執行緒、DB + **同步 IOTA 上鏈** | `upload_to_blockchain()` 以 `subprocess.run([npx, tsx, submit_firmware.ts, ...])` **同步**執行 IOTA 上鏈（`timeout=IOTA_SUBPROCESS_TIMEOUT` 預設 120s，bounded retry 預設 3 次 × 5s sleep）。**在單一 request lifecycle 內同步阻塞 worker**（見 §7）。 |
| Upload history | `GET /upload_firmware/history/` | DB 讀取 | 只讀 + 分页（`select_related` 避免 N+1），本身不重，但跑在單 worker 上。 |
| Firmware download request | `POST /transfer_firmware/request_download/` | 產生 signed URL（cache 寫入） | 輕量。 |
| Firmware download | `GET /transfer_firmware/download/<token>/` | 讀 cache + DB `FileResponse` | 中量（檔案流式回應）。 |
| admin | `/admin/` | Django admin | 未對外暴露。 |

## 4. 現有 k6 測試盤點

- `thesis/load_tests/` 下**沒有任何針對 Manufacturer Agent 的既有 k6 腳本**（所有既有腳本 `load-test.js` 皆針對 Customer Agent API `/api/customer/<id>/...`）。
- `results/v2/*.json`、`v2_k6_soak30.json` 等全部是 Customer Agent 的結果。
- 因此本次**建立** `thesis/load_tests/manufacturer-history-test.js`（最小、只讀、針對 `GET /upload_firmware/history/`，經 nginx mTLS 8443 → port-forward 到 host 18444），量測並行行為。

## 5. 新量測結果（before，僅Manufacturer Agent 現況，未修）

### 5.1 同 pod 內 8 並發（直接打到 `manufacturer-agent:8000`，不經 nginx）

```
req=3 http=400 time=0.215759s
req=6 http=400 time=0.357379s
req=1 http=400 time=24.811364s
req=2 http=400 time=24.809653s
req=8 http=400 time=24.638975s
req=7 http=400 time=27.973807s
req=4 http=400 time=28.095915s
req=5 http=400 time=28.076932s
```

（400 是 `ALLOWED_HOSTS` 缺失 `localhost` 導致的 `DisallowedHost`，是既有配置行為，非本次重點；重點是**同一 8 個並發請求中，前 2 個 ~0.2–0.4s，其餘 6 個全部堆到 24–28s**，清楚呈現 head-of-line blocking 序列化的遲滯分布。）

### 5.2 k6 經 nginx mTLS（8443）→ port-forward（host 18444）

| VU | 時長 | RPS | p50（iteration_duration）| p95 | 100% 請求皆 `http_req_failed`（TLS 未授權驗證失敗，見 §5.3） |
|---:|---:|---:|---:|---:|---|
| 10 | 2m | 14.4 | 0.65s | 1.25s | 1741/1741 |
| 30 | 2m | 24.4 | 1.14s | 2.11s | 2944/2944 |
| 50 | 3m | 25.9 | 1.67s | 3.87s | 4116/4116 |
| 50 | 60s | 25.4 | 1.82s | 3.01s | 1576/1576 |

- RPS 隨 VU 數上升**幾乎不成長**（v30→v50：24.4→25.9 RPS，v50→v50(60s) 也維持 ~25 RPS），與 Customer Agent 修復前「v50→v100 RPS 9.35→10.38 幾乎不長」的 head-of-line 特徵一致。
- p50/p95 隨 VU 數上升而明顯拉長（1.14s→1.67s→1.82s），代表請求在佇列中堆積。

### 5.3 額外發現：k6 對 mTLS 端點 100% `http_req_failed`

- 所有 k6 請求回報 `tls: failed to verify certificate: x509: certificate signed by unknown authority` — k6 端未帶 mTLS client cert（`insecureSkipTLSVerify` 只跳 server 端驗證，**不**提供 client cert），而 nginx 8443 端是 `ssl_verify_client on`（強制 client cert）。
- 因此本次 k6 量測到的是「TLS 被拒」的錯誤路徑，非真實 business 成功路徑；**RPS 幾乎不隨 VU 成長**這個特徵仍有價值（因為 TLS 拒回本身極快，若後端能吸收並發，RPS 應該會隨 VU 線性上升，而非卡在 ~25 RPS），代表**瓶頸確實卡在製造商後端的單一 worker**，而非 TLS 驗證本身。
- 若要量「成功路徑」的真實 p95/p99，需另建 k6 端帶 mTLS client cert 的設定（`K6MILK` env / `--client-cas`），本次未做。

## 6. 結論：Manufacturer Agent 有相同的 single-worker bottleneck

**證據鏈**：
1. 架構層：Django WSGI + `werkzeug.serving.run_simple()`，Pod 內 `ps` 只有單一 `python run_manufacturer_agent.py` process（已親自在 3 個 pod 上確認），與 Customer Agent 修復前完全一致。
2. 資源層：cpu/memory limits 與 Customer Agent 修復前完全相同（cpu=250m / mem=256Mi）。
3. 量測層：8 並發下 6/8 個請求堆到 24–28s（head-of-line 序列化）；k6 v30→v50 RPS 幾乎不上升、p50/p95 隨 VU 拉長。
4. 既有 k6 結果：無 Manufacturer 端既有測試（全數是 Customer 端），無可對照的 before/after 數字，但本次**新建**的最小 k6 已足以證明「同樣的 head-of-line 特徵存在」。

**與 Customer Agent 不同之處**（不要直接套用同一張處方）：
- Manufacturer 端的 CPU limits 極低（250m），gunicorn 4 worker 在 250m 上會比 Customer 端（同樣 250m，但已證實 gunicorn 4 worker 可跑且 HPA 3→4）更容易觸發 cgroup throttling，需实测決定 worker 數。
- Manufacturer 端 `POST /upload_firmware/upload/` 內嵌**同步** IOTA 上鏈（`subprocess.run` `npx tsx`，120s timeout × 最多 3 retries + 5s sleep ≈ 最壞 ~4s/次 × 3 ≈ 最壞 ~12–16s 的 worker 占用），這個**長執行緒同步 I/O 阻塞**與 Customer 端 `run_periodic_query` 背景 thread（非 request 路徑）不同 — 製造商端的長阻塞**直接卡在 request 處理路徑上**，是比 Customer 端更嚴峻的「request lifecycle 內同步阻塞」問題，即使換 Gunicorn 多 worker，若 4 個 worker 同時都被 upload 長阻塞占住，仍會出現「4 worker 全卡住」的類似 head-of-line 效應，只是並發容忍度提高 4 倍。

## 7. IOTA 阻塞問題（特別注意項）

`thesis/manufacturer_agent/upload_firmware/views.py` `UploadFirmwareAPIView.post()` 結尾：

```python
try:
    upload_to_blockchain(firmware_metadata)   # 同步 subprocess npx tsx ...
    return ManufacturerUploadRespond("Firmware uploaded successfully")
except Exception as e:
    return ManufacturerUploadRespond(message=str(e), error_code=500, http_status=500)
```

`upload_to_blockchain()` 內：
- `subprocess.run([npx, "tsx", SUBMIT_FIRMWARE_TS_PATH, ...], capture_output=True, text=True, timeout=IOTA_SUBPROCESS_TIMEOUT)`，`IOTA_SUBPROCESS_TIMEOUT` 預設 **120s**。
- bounded retry：`max_retries` 預設 3（`IOTA_MAX_RETRIES`），每次失敗間 `time.sleep(retry_interval)`（預設 5s）。
- **整個流程在單一 HTTP request 的 worker 內同步執行**，即：

```
POST /upload_firmware/upload/
   → Django view (單 worker 內的該 request)
      → subprocess.run(npx tsx submit_firmware.ts)   # 同步等 IOTA 回傳（最壞 120s/次）
      → 失敗再 sleep 5s × 3 次
      → 全過程該 worker 完全被此 request 占用
```

- 這代表**即使換成 Gunicorn 4 worker**，若 4 個 worker 同時都收到 upload 請求、且 IOTA 端延遲/超时，仍會出現「4 worker 全數被 IOTA subprocess 占滿、其他 history/download 請求全數堆隊列」的新一層 head-of-line。這與 Customer 端「background periodic query thread 與 worker 競爭 GIL」不同 — 製造商端是「request 處理路徑本身包含同步長 I/O」，是更具體、更直接的 bottleneck。

**證據**：`grep -n "upload_to_blockchain" thesis/manufacturer_agent/upload_firmware/views.py` 可看到 `try: upload_to_blockchain(...)` 直接嵌在 `post()` 方法內，無 threading/async/Celery 卸載。

## 8. HPA 狀態

- `manufacturer-agent` HPA（min=3/max=4 @ CPU 75%）：目前 `cpu: 5%/75%`，3 replicas，**無 scale-up 事件**（`kubectl get events -n thesis` 只看到 `FailedGetResourceMetric` 警告，與 Customer 端早期 metrics-server 抖動相同，非本次負載導致的 rescale）。
- 因本次未做 30 分鐘 soak 重測（僅做最小 v30/v50 兩檔），**HPA 狀態 = NOT VERIFIED**（無負載下未觸發，也不該強求它在 5% CPU 下觸發）。

## 9. 建議（未執行，待用戶決定）

1. **最小同方向修復**（與 Customer 端一致，針對 head-of-line 問題）：
   - `run_manufacturer_agent.py` 改為 `gunicorn` 啟動（**worker 數依 250m CPU limit 建議 2，不是 4** — 4 worker × 250m 極易超 cgroup 上限；Customer 端之所以可用 4 是因為該 pod 實際吃到 70–84% CPU 後由 HPA 擴到 4 個 pod 分攤，製造商端目前負載低，2 worker 已足夠解決 head-of-line 問題且較不易觸發 throttling）。
   - Nginx `manufacturer.conf` 不變（已為 plain HTTP upstream，gunicorn 可直接接）。
   - 需重 build `thesis/manufacturer-agent:local` 並 rollout。
2. **IOTA 長阻塞獨立處理**（不屬於「一次只處理一個瓶頸」的最小修復，建議拆成獨立任務）：
   - 將 `upload_to_blockchain()` 改為非同步（例：DB 記錄落盤後即回 200，IOTA 上鏈由獨 lập background worker / `django-q` / `celery` 或獨立 CronJob 依 `SubmitBlockRecord` 狀態補發），避免 request lifecycle 內同步 `subprocess.run` 阻塞 Gunicorn worker。
   - 此處刻意不在本次「最小修復」中一併改動（避免一次改太多、且與 user 指示「不要因為 Customer 已修成 Gunicorn 就直接假設 Manufacturer 也必須修改」一致 — 先確認 head-of-line 有無，再單獨處理 IOTA）。
3. **k6 mTLS 測試缺口**：`manufacturer-history-test.js` 目前只能量「TLS 被拒」路徑的 RPS/latency 特徵（足以證明 head-of-line，但非 business 成功路徑）；若要精準 before/after p95/p99，需補一版 k6 帶 mTLS client cert（`K6MILK`）的測試腳本。

## 10. 最終格式回報

### Root Cause
Manufacturer Agent 同樣存在「Django WSGI → Werkzeug `run_simple()` → 單 worker」的架構，與 Customer Agent 修復前完全相同；且額外存在 `POST /upload_firmware/upload/` 內**同步**執行 IOTA `subprocess.run`（`npx tsx`，120s timeout × 最多 3 retries + 5s sleep）的長阻塞，是比 Customer 端更具體的 request-lifecycle 同步阻塞問題。

### Evidence
- `kubectl exec ... sh -c "cat /proc/*/cmdline"`：3 個製造商 pod 皆只有單一 `python run_manufacturer_agent.py` process。
- 同 pod 8 並發直連 `manufacturer-agent:8000/upload_firmware/history/`：2/8 個 ~0.2–0.4s，6/8 個堆到 24–28s（head-of-line 序列化遲滯分布）。
- k6（經 nginx mTLS 8443 → port-forward 18444，TLS 未授權路徑）：v30→v50 RPS 從 24.4 → 25.9 幾乎不上升；p50 從 1.14s → 1.67s/1.82s 隨 VU 拉長。
- resource limits：`cpu=250m / memory=256Mi`（與 Customer Agent 修復前完全相同）。

### Before
```
Nginx (8443 mTLS, 終端)
   ↓ proxy_pass http://manufacturer-agent:8000/
Django WSGI (run_manufacturer_agent.py, run_simple())
   ↓
Werkzeug 開發伺服器
   ↓
1 個單執行緒 worker（python PID 1）
```
- CPU limit 250m（cgroup 已見 `nr_throttled=574`，低負載下）
- 8 並發：6/8 請求 24–28s
- k6 v50（TLS 未授權路徑）：RPS ~25.9，p50 1.67s，p95 3.87s

### Fix（建議、未執行）
```
Nginx (8443 mTLS, 終端)
   ↓ proxy_pass http://manufacturer-agent:8000/
Gunicorn (bind 0.0.0.0:8000, plain HTTP)
   ├── Worker 1
   └── Worker 2   (依 250m CPU limit 建議 2 個，不是 4)
```
- 改動範圍：`run_manufacturer_agent.py`（Gunicorn 啟動）、`Dockerfile.manufacturer-agent`（不需改，`CMD` 可繼續指向同一檔，只是內部改動）、重 build `thesis/manufacturer-agent:local`、rollout。
- Nginx 端**不需改**（已是 plain HTTP upstream）。
- IOTA 同步阻塞獨立拆出（不屬於本次最小修復）。

### After
未量測（未執行 Fix）。

### HPA
NOT VERIFIED（目前無負載，HPA 維持 3 replicas @ cpu 5%；未做 30min soak 重測，無法斷言 scale-up/down 行為）。

### Remaining Issues
1. IOTA `subprocess.run` 同步阻塞 request lifecycle（見 §7），即使換 Gunicorn 仍會造成 worker 被長占用 — 需獨立處理（拆成 background worker / Celery / CronJob）。
2. k6 對 mTLS 端點的測試缺口（未帶 client cert，只能量「被拒」路徑），若要精準 business 成功路徑 before/after，需補 K6MILK 版本。
3. 本次未做 30 分鐘 soak 重測，HPA 狀態僅為 NOT VERIFIED，非 PASS/FAIL 結論。
4. 250m CPU limit 對 Gunicorn worker 數是硬上限 — 需实测決定 2 vs 4 worker（建議 2，避免 cgroup throttling）。
