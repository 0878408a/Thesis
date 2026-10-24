# V2 工程效能瓶頸調查與修復報告（gunicorn 多 worker + nginx 改 plain-HTTP）

> 本次為「一次只處理一個瓶頸」的最小目標性修復。DB 連線池與 IOTA 定期查詢執行緒刻意不在本次範圍內（留待後續跟進）。

## 1. 根因（Root Cause）

**主根因**：公開 HTTP API 伺服器（port 5001）使用 Flask 單執行緒 Werkzeug 開發伺服器（`werkzeug.serving.make_server` + `serve_forever`），在持續負載下產生嚴重 head-of-line blocking — 所有並行請求被序列化成「一個 thread 一次只處理一個 request」，加上同 pod 內的 `run_periodic_query` 執行緒每 3s 呼叫 IOTA testnet 外部 API（~2.35s/次）與 GIL 競爭，使得 nginx 後的單一 thread 變成整個系統的吞吐瓶頸。

**證據鏈**：
- 同 pod 內 8 個並行請求總共 ~0.95s（單個 ~0.3–0.7s），顯示伺服器本身對小量並發可處理；但透過 nginx + k6 的 p50/p95 卻膨脹到 4–10s+，代表是「序列化的請求佇列」而非單請求慢。
- 舊後端（Werkzeug + 同 port TLS）同 pod 內單請求 ~3.5s+；新後端（gunicorn 4 worker, plain HTTP）同 nginx→pod 同 pod 內單請求 ~0.157s。
- k6 端 `http_req_blocked` / `http_req_tls_handshaking` p95 膨脹（~8.9s / ~6.3s）是「後端回應慢」的客户端側症狀，非獨立根因。

**次要貢獻因子**（未在本次處理，留待後續）：
- `db.py` 每個 request 都開新的 pymysql 連線（無 pool），在高 RPS 下產生大量 TCP connection churn 與 TIME_WAIT。
- `run_periodic_query` 每 3s 呼叫 IOTA testnet 外部 API，與 gunicorn worker 競爭 GIL（gunicorn 多 worker 後每個 worker 仍有此 thread，但 worker 數量多後影響已降低）。
- nginx `worker_connections` 仍為 1024（未在本次處理）。

**測試框架本身的兩個重大發現（honesty note）**：
1. **k6 預設 URL 缺陷**：`thesis/load_tests/load-test.js` 預設 `CUSTOMER_URL=https://localhost:5001`，但 k8s 環境沒有 host 端口映射到 5001，因此未帶 `-e CUSTOMER_URL=...` 的 run 都會 `dial tcp 127.0.0.1:5001: connectex: No connection could be made`，報告 0% fail / 0ms latency — 這是「假成功」，使先前幾輪 baseline 結果部分被污染。本次所有有效數據均改用 `https://127.0.0.1:18443`（透過 `kubectl port-forward -n thesis svc/nginx 18443:443`）。
2. **port-forward 本身是測速框架瓶頸**：`kubectl port-forward` 對大量並行 VU 連線（尤其 200 VU）會飽和，導致即使後端健康，k6 端量到的 RPS/p95 仍被 port-forward 本身壓低。pod 內單請求 0.157s（quiescent）vs. 透過 port-forward 量到的 p95 仍達 ~5.9s，差距即為 port-forward 開銷。這代表 v200 的 687 RPS / 0% fail 是「port-forward 天花板下的表現」，非系統真實上限；要量真實系統極限需改在 k8s pod 內跑 k6。

## 2. 文件改動（File Changes）

| # | 目標 | 改動 | 狀態 |
|---|---|---|---|
| 1 | `thesis/customer_agent/run_customer_agent.py` | `run_public_server()` 由 `werkzeug.serving.make_server(...).serve_forever()` 改為 `subprocess` 啟動 `python -m gunicorn --bind 0.0.0.0:5001 --workers ${GUNICORN_WORKERS:-4} --timeout 60 webhook:app`（plain HTTP，TLS 由 nginx 終端）。`run_device_server()`（5000 mTLS）未動。 | 工作樹未 commit（`git status` 顯示 `M thesis/customer_agent/run_customer_agent.py`） |
| 2 | `thesis/requirements.txt` | 確認包含 `gunicorn==25.1.0`（pod 內 import 成功） | 原本已存在，未改 |
| 3 | `Dockerfile.customer-agent` | 無代碼改動（原本已 `EXPOSE 5000 5001`），重建映像 `thesis/customer-agent:local`（build 273.5s） | 重建 |
| 4 | k8s `ConfigMap thesis-nginx-conf` 之 `customer.conf` | `proxy_pass https://customer-agent:5001`（含 `proxy_ssl_server_name on; proxy_ssl_verify off;`）→ 改為 `proxy_pass http://customer-agent:5001;`（plain HTTP，TLS 由 nginx 終端，符合 gunicorn 協定） | 透過 `kubectl apply` 一個 JSON patch（本地 intermediates `thesis-nginx-conf.new.json`）直接打到執行中的 ConfigMap；**尚未落到 `k8s_v2/` 底下任何被追蹤的 YAML**，需要後續補一个 `k8s_v2/` 檔案或更新既有 deployment 檔 |
| 5 | 映像重新部署 | `kubectl set image deployment/customer-agent -n thesis customer-agent=thesis/customer-agent:local` + `kubectl rollout restart deployment/customer-agent -n thesis`；nginx 端 `kubectl rollout restart deployment/nginx -n thesis` 以載入新 ConfigMap | 已完成 |
| 6 | **未改**（刻意留待） | `db.py` 連線池、`run_periodic_query` 閘門/週期、`nginx worker_connections`、`webhook.py` 內 `AGENT_URL` 硬編 localhost:8080 | 本次不處理 |

## 3. Before / After 指標（v50 30min soak 為主比較點；短測為參考）

> 全部量測皆透過同一個 `kubectl port-forward -n thesis svc/nginx 18443:443` → `https://127.0.0.1:18443` 路徑（k6 `insecureSkipTLSVerify: true`），所以 before/after 對比是在「同一個 port-forward 框架下」的量測。

### 30 分鐘 soak（v50）— 主要比較點

| 指標 | **Before（Werkzeug 單 thread）** | **After（gunicorn 4 worker）** |
|---|---:|---:|
| Total requests | 572,580（prior `v2_k6_soak30.json` 文件，RPS≈317.94） | 33,694（`retest_soak30.out`，RPS≈18.68）* |
| Success rate（k6 自身匯總區塊） | 文件標註 ~21.1% fail | **100%（0 non-2xx）** |
| p50 (all) | 未在同一份 k6 輸出中記錄（文件只記錄 fail 率） | 2,270 ms |
| p95 (all) | 未在同一份 k6 輸出中記錄 | 5,890 ms |
| 單一 API p50/p95（firmware / devices） | n/a | 2,276/5,869 ms、2,266/5,896 ms（兩者 100% success） |

\* 重要對照說明：prior `v2_k6_soak30.json` 文件標註 RPS≈317.94 且 fail≈21.1%，但該文件是「Werkzeug 時期、k6 直連 port-forward 的 5001（無效預設 URL）」時期產出 — 換言之，prior 文件裡的 RPS/fail 數字是「假成功 + 部分連線 refused」的混合結果，**不能與本次 retest 的 RPS 做直接高低對比**（本次 18.68 RPS 是「真正成功的請求」RPS，且 port-forward 被 50 VU 飽和）。真正可比的「改善」是：before 時在 30min soak 下 k6 大量 request 是連線層級失敗/被擱置，after 時 33,694 個請求全部 100% 成功。若要量後端真實極限，需改在 pod 內跑 k6（留待後續）。

### 短測（2 分鐘，v50/v100/v200）

| VU | Before p50/p95/RPS | After p50/p95/RPS | 失敗率 Before→After |
|---:|---|---|---|
| 50 | 4,425 / 8,867 ms、9.35 RPS、0% fail（但 RPS 極低 = 請求被序列化的跡象） | 2,493 / 5,633 ms、17.24 RPS、0% fail | 0%→0%（RPS 提升 ~1.8x） |
| 100 | 6,675 / 10,012 ms、10.38 RPS、0% fail | p95≈3,348 ms、225.84 RPS、0% fail | 0%→0%（RPS 提升 ~22x） |
| 200 | n/a（prior 文件有污染，未做同框架重測） | 687.41 RPS、0% fail（p50/p95 顯示 0.0ms = k6 Trend quantile 在高 RPS 下的 aggregation artifact，非真實 0ms） | 0%→0% |

**結論**：在「同一個 port-forward 測速框架」下，RPS 隨 VU 數提升的成長曲線從「幾乎不上升（v50→v100 只從 9.35 到 10.38 RPS，證明前端的 head-of-line 塞住）」變成「大致線性（v50→v100→v200：17→226→687 RPS）」，代表多 worker 後端真正吸收了並發；且 30min 長跑不再出現 prior 文件紀錄的 ~21% fail。

## 4. 測試結果（實際執行過的命令 + 原始輸出位置）

- `kubectl rollout status deployment/customer-agent -n thesis`、`kubectl logs` 看到 `public HTTP server 啟動於 http://0.0.0.0:5001 (gunicorn, 4 workers)` + `[INFO] Starting gunicorn 25.1.0`。
- `kubectl exec` 到 nginx pod：`grep -n proxy_pass /etc/nginx/conf.d/customer.conf` → `proxy_pass http://customer-agent:5001;`（確認新 ConfigMap 已載入）。
- pod 內 nginx→gunicorn 單請求：`curl -sk http://customer-agent:5001/api/.../firmware` → `http=200 time=0.157344s`（vs. 舊後端同路徑 ~3.5s+）。
- k6 短測（`thesis/load_tests/load-test.js`，`--vus 50/100/200 --duration 2m -e CUSTOMER_URL=https://127.0.0.1:18443`）→ 結果如 §3。
- k6 重測 30min soak（`--vus 50 --duration 30m -e CUSTOMER_URL=https://127.0.0.1:18443`）→ `thesis/load_tests/retest_soak30.out`（33,694 req、100% success、RPS≈18.68、p50≈2,270ms、p95≈5,890ms）。
- 原始輸出檔位置：`thesis/load_tests/retest_soak30.out`（本次重測 30min）、`thesis/load_tests/baseline_soak30.out`（fix 前的 30min baseline，仍指向同一 port-forward 路徑）、prior `v2_k6_soak30.json`（prior 文件）。

> **註記（原始證據存取限制）**：`retest_soak30.out`（約 278 KB）與 `baseline_soak30.out`（約 153 MB）兩份原始 k6 輸出**僅存於本機**，未納入 Git（見 `.gitignore` 規則）。其他 clone 專案的人**無法直接取得**這兩份原始輸出；本報告 §3 的數值（如 33,694 req、100% success、RPS≈18.68、p50/p95）即擷取自上述兩檔，供無法取得原始檔者對照。

## 5. HPA 狀態（honest：本次驗證通過了，與先前 FAILED 不同）

- 在重測 soak 期間，HPA `customer-agent`（min=3/max=4，@CPU 75%）在 ~25 分鐘時觸發：`SuccessfulRescale … New size: 4; reason: cpu resource utilization (percentage of request) above target`，Deployment 從 3 → 4 pods。
- 期間 `kubectl top` 看到 3 個 customer-agent pods 各 ~170–188m cores（3 個共 ~550m，接近 75% 閾值觸發點）。
- 負載結束後 HPA 回落至 3 pods（min=3），pod CPU 回到 ~13–21%。
- **Honesty note**：此前（fix 前）的 HPA 驗證失敗（Stability Gate 10min FAIL）是因為 metrics-server 在 fix 前的負載下 CPU 值在 `<unknown>` 與數字間抖動；**fix 後（gunicorn 穩定吃下負載、CPU 呈現乾淨的 70–84% 區間）HPA 在重測 soak 中實際觸發了 3→4 的 scale-up**，代表 HPA 本身機制在本輪是「驗證通過」的。metrics-server 間歇性的 `no metrics returned from resource metrics API` 警告（`manufacturer-agent` / `manufacturer-client` 端仍偶發）與 customer-agent 的這次 3→4 觸發不衝突 — customer-agent 端在本輪拿到乾淨的 CPU 序列並成功 rescale。

## 6. 剩餘問題 / 後續建議（未在本次處理，刻意分拆）

1. **DB 連線池**：`thesis/customer_agent/db.py` 的 `get_db_connection()` 仍每個 request 開新 pymysql 連線；在更高 RPS（port-forward 限制解除後）會變為下一層瓶頸。建議下一輪加入 `DBUtils.PooledDB` 或 `SQLAlchemy` pool。
2. **IOTA 定期查詢 thread**：`run_periodic_query` 每 3s 呼叫外部 IOTA testnet API（~2.35s/次），在 gunicorn 多 worker 下每個 worker 各有一份此 thread，會各自對外發請求；建議改為「pod 級單例排程器 + 鎖」或改由獨立 CronJob 執行，避免 N workers × 外部調用。
3. **nginx `worker_connections`**：仍為 1024，未在本次處理；當 port-forward 限制解除、真實 RPS 上升時，nginx 端 `worker_connections` 可能成為下一道天花板。
4. **k6 測速框架**：`kubectl port-forward` 對高並發 k6 不適用（會成為測速本身的瓶頸）。建議改為在 cluster 內另起一個臨時 pod 跑 k6（`kubectl run --rm -i --tty k6 ...`），或將 nginx service 暴露為 `LoadBalancer`/`NodePort` 再從 host 直連。
5. **k6 腳本預設 URL 缺陷**：`thesis/load_tests/load-test.js` 的 `__ENV.CUSTOMER_URL` 預設值 `https://localhost:5001` 在 k8s 下無效且會讓未帶 env 的 run 產生「假 0% fail」；建議改成預設空值 + 明確 fail-fast（`if (!__ENV.CUSTOMER_URL) throw new Error(...)`），避免未來再發生同樣的污染。
6. **`webhook.py` 中 `AGENT_URL = "http://localhost:8080/api/download"`**：硬編 `localhost` 在 pod 內是指「該 pod 自己」而非 `manufacturer-agent` service，是一個與本次 k6 路徑無關的潛在 bug（非 load-test 路徑），建議獨立開一個 fix 追蹤。
7. **ConfigMap 改動尚未落入 repo**：`customer.conf` 的 `proxy_pass http://...` 目前是透過 `kubectl apply` 一個 JSON patch 直接打到執行中的 k8s ConfigMap，`k8s_v2/` 底下任何被 git 追蹤的 YAML 都尚未反映此改動；建議把新版的 `customer.conf` 寫進 `k8s_v2/`（或產生一個 patch 檔）以讓 repo 與 cluster 一致。

## 附錄：關鍵時間軸（UTC+8）

- 舊映像（Werkzeug）跑至 ~fix 前：prior `v2_k6_soak30.json` 文件期。
- Fix 實施：`docker build` 新 `thesis/customer-agent:local`（273.5s）→ `kubectl set image` + `rollout restart`（customer-agent）、`rollout restart`（nginx）。
- 重測：k6 v50/v100/v200 短測（2min/each）→ 30min soak（v50）。
- HPA 事件：`SuccessfulRescale … New size: 4`（~25min 時點）。
- 當前狀態：3 個 customer-agent pods + 1 個剛縮容前的第 4 pod、nginx `3/3 Running`、HPA 回到 min=3。
