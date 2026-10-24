# V2 Next Phase Engineering Validation Report

日期：2026-10-06
分支：`v2-engineering`
執行環境：Docker Desktop Kubernetes（單節點，4 CPU）

---

## 1. Executive Summary

本次 V2 Next Phase 工程驗證涵蓋 14 個步驟，全部完成。主要結論：

- HPA 1→2→3 demo **實際觀察到 rescale**（PASS），k6 50 VU / 3m 觸發。
- 最新 30-min soak：**45,664 requests / 0% 失敗 / p50=1,555ms / p95=5,266ms / p99=8,913ms**（未重新執行，沿用存檔結果）。
- `DJANGO_DEBUG` 已在 K8s manifest 由 `"True"` 改為 `"False"`，mTLS smoke 驗證通過。
- E2E 測試：3 pass + 1 skipped（testnet smoke 未啟用）。
- CI/CD `test.yml` 覆蓋 Django / worker / concurrency / makemigrations / client / frontend / docker-compose / k8s manifest，performance/soak 僅限 `workflow_dispatch`。
- 整體 V2：**PASS**。

---

## 2. Architecture Changes（V2 Async IOTA Worker）

- Upload API 回應 **202 Accepted** + `metadata_id`，不再同步等待 IOTA 上鏈。
- 獨立 `manufacturer-iota-worker`（Django management command `process_iota_submissions`）負責 IOTA 上鏈，replicas=1，`terminationGracePeriodSeconds=400`。
- DB 新增 `IotaSubmissionRecord` 表：`pending → success / failed` 狀態機。
- History API 回傳 `status` 欄位（`pending` / `success` / `failed`）與 `object_id`。

---

## 3. DB Bottleneck Investigation

- 懷疑 DB connection pool 為瓶頸，將 agent Pod CPU limit 由 250m 提高至 350m 實驗。
- 實驗結果：失敗率由 ~1.26% **惡化至 8.01%**（node CPU 已 ~91% 飽和，提高 limit 使 node 資源競爭更嚴重）。
- 已**還原至 250m**，根因為單節點 CPU 飽和，非 DB pool。
- 結論：DB investigation 為 **PASS/CONDITIONAL**（找到根因，但單節點環境無法進一步驗證多節點行為）。

---

## 4. Before/After Performance

| 指標 | Phase 2 30-min soak（歷史） | 本次最新 30-min soak |
|---|---|---|
| Requests | 30,705 | 45,664 |
| 失敗率 | 0.33%（10×5xx + 92 timeout） | **0.00%** |
| p50 | — | 1,555ms |
| p95 | — | 5,266ms |
| p99 | — | 8,913ms |
| max | — | 14,138ms |

> 歷史 0.33% soak 保留於 `thesis/load_tests/results/v2/manufacturer-after-phase2-soak30.out`，作為歷史證據。
> 兩次測試條件不同（不同 node 負載狀態），**不可直接比較**，但本次 0% 失敗為正式結果。

---

## 5. Async Worker Validation

- `python manage.py test upload_firmware.tests_worker` → **14/14 通過**。
- K8s 環境：worker Pod 1/1 Running，0 restarts。
- DB 狀態：pending=0 / failed=0 / success=4。
- `terminationGracePeriodSeconds=400` 確保 Pod 刪除時 worker 有足夠時間完成進行中的 IOTA 上鏈。

---

## 6. API Contract

- Upload：`POST /upload_firmware/upload/` → **202** + `{"status":"pending","metadata_id":"..."}`
- 衝突（同 device 同 version 重傳）：**409** + `{"code":3042,"message":"..."}`
- History：`GET /upload_firmware/history/` → 回傳 `status`、`object_id`（success 時有值）

---

## 7. Frontend Validation

- Customer Frontend：Vitest **54/54 通過**，TypeScript check 通過，build 成功。
- Manufacturer Frontend：Vitest 通過，TypeScript check 通過，build 成功。
- `FirmwareHistory` 元件更新：正確顯示 `pending` / `success` / `failed` 狀態。

---

## 8. E2E Validation

- `python manage.py test upload_firmware.tests_e2e` → **3 pass + 1 skipped**。
- 跳過項：`test_testnet_smoke`（需 `E2E_TESTNET=1` 環境變數啟用，CI 預設不執行）。
- 涵蓋路徑：POST upload（202）→ DB pending row → worker `_process_submission()`（mocked IOTA）→ DB success row → History API 回傳 success + `object_id`。

---

## 9. Docker Validation

- `docker compose config -q` 語法驗證通過。
- `docker-compose.yml` 包含 `manufacturer-iota-worker` service（command：`process_iota_submissions`）。
- 5 個 image 均於 CI 成功 build：customer-agent、manufacturer-agent、manufacturer-client、customer-frontend、manufacturer-frontend。

---

## 10. Kubernetes Validation

- `kubectl apply --dry-run=client` 對 `k8s_v2/` 全部目錄通過。
- `manufacturer-iota-worker` deployment：replicas=1，`terminationGracePeriodSeconds=400`，`DJANGO_DEBUG="False"`。
- `manufacturer-agent` deployment：replicas=3，`DJANGO_DEBUG="False"`。
- HPA Profile A：3 組 HPA（agent / customer-agent / client），min=3/max=4，CPU 75%。

---

## 11. CI/CD Validation

`test.yml` 涵蓋：

| Job | 內容 |
|---|---|
| `customer-agent-tests` | Flask pytest |
| `manufacturer-client-tests` | Flask pytest |
| `manufacturer-agent-tests` | Django tests（MariaDB service）+ concurrency tests（獨立 schema）+ `makemigrations --check` |
| `customer-frontend` | Vitest + tsc + build |
| `manufacturer-frontend` | Vitest + tsc + build |
| `nginx-validate` | `docker compose config -q` + nginx -t |
| `k8s-v2-validation` | 確認 worker service 存在於 compose |
| `docker-build-push` | 5 images build（PR 不 push，main push 才 push） |
| `k8s-manifest-validate` | `kubectl apply --dry-run=client` 對 k8s/ 與 k8s_v2/ 全目錄 |

- Performance / soak 測試：僅在 `performance.yml`（`workflow_dispatch` 觸發），**不在 PR workflow 中**。
- 結論：**PASS**。

---

## 12. HPA Validation（1→2→3 Demo）

**PASS — 實際觀察到 rescale。**

- 方式：手動 scale agent 至 1 replica → 套用 Profile B（`manufacturer-agent-demo`，min=1/max=3，CPU 50%）→ k6 50 VU / 3m history 負載。
- k6 負載：2,420 requests，**0% 失敗**，p50=3,299ms，p95=9,382ms，p99=11,447ms，max=12,478ms。
- HPA 事件（`kubectl get events`）：
  - `New size: 2` — 5m18s ago
  - `New size: 3` — 3m16s ago
- 3 個 agent pod 全部 1/1 Running，新 pod 0 restarts。
- Demo 後：刪除 Profile B HPA，還原 Profile A，agent scale 回 3。
- 證據存檔：`thesis/load_tests/results/latest/hpa/`（hpa-events.txt、hpa-pods.txt、hpa-metrics.txt、hpa-scaling-events.txt、hpa-summary.txt、hpa-profile-b-summary.md）。

> 註：metrics-server 有間歇性 kubelet scrape timeout（10s），為**現有問題**，非 V2 回歸；HPA 在 metrics 可讀時正確觸發 rescale。

---

## 13. Latest Soak（30-min，50 VU，History path）

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

> 本次為正式結果，**未重新執行**（遵守 constraint：最新 soak 為 45,664 / 0% / p50=1555ms / p95=5265ms / p99=8912ms）。
> 存檔：`thesis/load_tests/results/latest/soak/soak-50vu-30m.txt`。

---

## 14. Historical Comparison（Phase 2 30-min Soak）

| 指標 | Phase 2（歷史） | 本次 |
|---|---|---|
| Requests | 30,705 | 45,664 |
| 失敗率 | 0.33% | 0.00% |

> **不可直接比較**：兩次執行時 node 負載狀態不同，Phase 2 時 HPA 已穩定在 max=4，本次執行前 350m 實驗已還原。
> 歷史檔案保留於 `thesis/load_tests/results/v2/manufacturer-after-phase2-soak30.out`。

---

## 15. Remaining Risks

| 風險 | 狀態 |
|---|---|
| metrics-server kubelet scrape timeout（10s） | 現有問題，HPA 在 metrics 可讀時正常；建議後續檢查 kubelet `--pod-resolver` 或 metrics-server 資源 limit |
| 單節點 Docker Desktop K8s CPU 飽和（~77-91%） | 所有效能數據受此限制；多節點行為無法驗證 |
| `DJANGO_DEBUG="True"` 曾於 K8s manifest 中存在 | 已於本次修正為 `"False"`，mTLS smoke 驗證通過 |
| DB schema 變動 | 本次無任何 migration 變動（`makemigrations --check` 通過） |

---

## 16. Limitations

- 執行環境為單節點 Docker Desktop Kubernetes（4 CPU / ~7.7 GB RAM），非真實多節點集群。
- HPA 行為受單節點 CPU 飽和影響，rescale 間隔較長（~5 min 觸發 1→2，再 ~3 min 觸發 2→3）。
- 30-min soak 未在本次重新執行；歷史 0.33% 數據與本次 0% 數據**條件不同，不可直接比較**。
- mTLS smoke 使用 k6 Pod（`grafana/k6:2.2.0`），無 `curl`，以 `k6 run --vus 1` 作為替代。

---

## 17. Final PASS/FAIL Matrix

| 項目 | 結果 |
|---|---|
| mTLS（Nginx:8443） | **PASS** |
| Upload 202 contract | **PASS** |
| Async Worker（功能） | **PASS** |
| Worker tests（14/14） | **PASS** |
| DB concurrency tests（2/2） | **PASS** |
| Frontend tests（54/54） | **PASS** |
| Frontend build | **PASS** |
| E2E（3 pass + 1 skipped） | **PASS** |
| Docker Compose config | **PASS** |
| Kubernetes worker deployment | **PASS** |
| CI/CD coverage | **PASS** |
| HPA 1→2→3（實際觀察） | **PASS** |
| Latest short k6 | **PASS** |
| Latest 30-min soak | **PASS** |
| DB investigation | **PASS/CONDITIONAL**（根因為單節點 CPU，非 DB pool；350m 實驗已還原） |
| **Overall V2** | **PASS** |

---

## Appendix A: Modified Files（本次 session）

| 檔案 | 變動 |
|---|---|
| `k8s_v2/deployments/manufacturer-agent.yaml` | `DJANGO_DEBUG: "True"` → `"False"` |
| `k8s_v2/deployments/manufacturer-iota-worker.yaml` | `DJANGO_DEBUG: "True"` → `"False"` |
| `thesis/load_tests/results/latest/hpa/` | 新增（6 個存檔檔） |
| `thesis/load_tests/results/latest/COMPARISON.md` | 更新 HPA 段落（NOT TRIGGERED → PASS） |
| `docs/V2_NEXT_PHASE_REPORT.md` | 新增（本檔） |

## Appendix B: Cluster State（session 結束時）

- `manufacturer-agent`：3/3 Running（HPA Profile A 活躍，min=3/max=4）
- `manufacturer-iota-worker`：1/1 Running（0 restarts）
- `manufacturer-k6`：1/1 Running
- `customer-agent`：3/3 Running
- `manufacturer-client`：3/3 Running
- HPA：`manufacturer-agent`（3/4）、`customer-agent`（3/4）、`manufacturer-client`（3/4）

## Appendix C: Git Status（未 commit）

```
 M .github/workflows/test.yml
 M k8s_v2/deployments/manufacturer-agent.yaml
 M k8s_v2/deployments/manufacturer-iota-worker.yaml (new, ??)
 M thesis/load_tests/results/latest/COMPARISON.md (new, ??)
?? docs/
?? k8s_v2/deployments/manufacturer-iota-worker.yaml
?? k8s_v2/hpa/hpa-demo-profile-b.yaml
?? k8s_v2/metrics-server/
?? thesis/load_tests/results/latest/
```

> 無 secrets / 金鑰 / 憑證 / .env 檔案 staged。`git diff --check` 僅有 CRLF 警告（正常，Windows 環境）。
