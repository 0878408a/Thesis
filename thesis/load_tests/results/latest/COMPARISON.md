# V2 k6 比較表（2026-10-06）

所有數據均為 **in-cluster mTLS**（`manufacturer-k6` Pod → `https://nginx:8443`），無 port-forward、無 TLS 驗證 bypass。

## 測試環境

- Docker Desktop Kubernetes 單節點（4 CPU / ~7.7 GB RAM）
- Manufacturer Agent：Gunicorn 2 sync workers × 3 replicas（HPA min=3/max=4，CPU target 75%）
- Agent Pod CPU limit：250m（350m 實驗已還原，見 `v2-next-phase-baseline.md`）
- k6 Pod：`grafana/k6:2.2.0`，掛載 `thesis-manufacturer-client-certs`（CA + client cert/key）

---

## 歷史數據（read path = History API）

| 階段 | 腳本 | VU / 時長 | Requests | RPS | 失敗率 | p50 | p95 | p99 |
|---|---|---|---|---|---|---|---|---|
| Before（Werkzeug） | `../v2/manufacturer-before-vu100.out` | 100 / 2m | — | — | — | — | — | — |
| Phase 1（Gunicorn） | `../v2/manufacturer-after-phase1-vu100.out` | 100 / 2m | 2,465 | 20.54 | 0.00% | 2,857ms | 7,749ms | 11,190ms |
| Phase 2（Async IOTA） | `../v2/manufacturer-after-phase2-vu100.out` | 100 / 2m | 2,636 | 21.15 | 0.04% | 3,883ms | 9,011ms | 11,219ms |
| **本次 baseline** | `v2-next-phase-baseline.md` §controlled | 100 / 2m | 1,744 | 13.20 | **1.26%** | 4,642ms | **18,116ms** | 20,008ms |
| 350m 實驗（還原） | `v2-next-phase-baseline.md` §Phase 2 | 100 / 2m | 1,535 | 12.18 | **8.01%** | 4,814ms | 20,096ms | 23,002ms |
| **本次 re-run** | `latest/short/history-100vu-2m.txt` | 100 / 2m | 3,385 | 27.02 | **0.00%** | 3,173ms | 7,525ms | 9,215ms |

> 本次 baseline（1.26% 失敗）與 re-run（0% 失敗）差異來源：baseline 執行時 node CPU ~91% 飽和；re-run 在 30-min soak 之前執行，node 負載較低。

---

## 本次短測（Upload path，fake signature → 400 為預期）

| VU | Requests | RPS | p50 | p95 | p99 | checks failed |
|---|---|---|---|---|---|---|
| 10 | 1,456 | 12.09 | 595ms | 1,578ms | 2,606ms | 10 |
| 50 | 2,458 | 19.84 | 2,168ms | 5,218ms | 6,595ms | 0 |
| 100 | 2,676 | 21.05 | 4,243ms | 7,934ms | 8,974ms | 0 |

> Upload 腳本使用 fake ECDSA signature，端點回 400（簽名驗證失敗）為設計行為，非功能錯誤。
> 此路徑測量的是 DB 寫入 + 請求處理吞吐量，非 IOTA 上鏈成功率。

---

## 本次 30-min Soak（History path，50 VU）

| 指標 | 數值 |
|---|---|
| Requests | 45,664 |
| RPS | 25.33 |
| 失敗率 | **0.00%**（0 5xx，0 4xx，0 timeout） |
| p50 | 1,555ms |
| p90 | 4,030ms |
| p95 | 5,266ms |
| p99 | 8,913ms |
| max | 14,138ms |

> **與 Phase 2 baseline 30-min soak 比較**：Phase 2 為 0.33% 失敗（10 筆 5xx DB TCP connect error，92 筆 timeout）；本次 0% 失敗。
> 差異來源：本次在 350m 實驗還原至 250m 後執行，且 HPA 維持 4 replicas（Phase 2 時 HPA 已穩定在 max=4）。

---

## HPA 狀態（執行期間）

- Profile A HPA（`manufacturer-agent`，min=3/max=4，CPU 75%）在 soak 期間維持 4 replicas。

### HPA 1→2→3 Demo（Profile B，k6 50 VU / 3m）

- 執行於 2026-10-06，k6 Pod → in-cluster mTLS（`https://nginx:8443`）
- 觸發方式：將 agent 手動 scale 至 1 replica → 套用 Profile B（min=1/max=3，CPU 50%）→ k6 50 VU / 3m history 負載
- 觀察結果：
  - HPA `manufacturer-agent-demo` 於 5m18s 觸發 1→2 擴展
  - HPA 於 3m16s 觸發 2→3 擴展
  - 3 個 agent pod 全部 1/1 Running
- k6 負載：2,420 requests，0% 失敗，p50=3,299ms，p95=9,382ms，p99=11,447ms，max=12,478ms
- Demo 完成後：刪除 Profile B HPA，還原 Profile A，agent scale 回 3
- 證據存檔：`latest/hpa/hpa-profile-b-summary.md` 及同目錄 .txt 檔

> 註：Demo 期間 metrics-server 有間歇性 kubelet scrape timeout（現有問題，非 V2 回歸），HPA 在 metrics 可讀時正確觸發 rescale。

---

## 結論

1. **Read path（History API）**：本次 re-run 100 VU 0% 失敗、p95 7.5s，優於 baseline 的 1.26% 失敗率。
   主要差異來自執行時 node 負載狀態，非程式碼變動。
2. **Write path（Upload，400 by design）**：100 VU 下 p95 7.9s，與 read path 相當；無 5xx。
3. **30-min soak**：本次 0% 失敗（對比 Phase 2 的 0.33%），單節點 CPU 飽和為主要瓶頸，非 DB connection pool 或慢查詢。
4. **350m CPU limit 實驗**：已還原，證據顯示提高 limit 在單節點 CPU 飽和環境下反而**惡化**效能。
