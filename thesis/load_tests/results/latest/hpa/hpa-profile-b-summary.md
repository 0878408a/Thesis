# HPA 1→2→3 Demo — 2026-10-07

## 結果:HPA 1→3 = **PASS**

實際觀察到完整 1→2→3 序列,非僅 YAML 設定值。

## HPA Profile B 設定

- `minReplicas = 1`, `maxReplicas = 3`, CPU target = 50%
- 檔案:`k8s_v2/hpa/hpa-demo-profile-b.yaml`

## Load 來源

- in-cluster k6 pod(`manufacturer-k6`),mTLS via `https://nginx:8443`
- script:`/scripts/manufacturer-history-test.js`,50 VU / 3 min
- k6 結果:2,420 requests,0% failure, p50=3299ms, p95=9382ms, p99=11447ms, max=12478ms

## 實際 Rescale 事件(依時間順序)

| 時間 | 事件 | 副本數 |
|---|---|---|
| (demo 前) | 手動 scale 1 + HPA below target | 1 |
| +5m18s | `SuccessfulRescale New size: 2; reason: cpu above target` | 1→2 |
| +3m16s | `SuccessfulRescale New size: 3; reason: cpu above target` | 2→3 |

## Pod 狀態(demo 完成後)

| Pod | READY | STATUS | RESTARTS | AGE |
|---|---|---|---|---|
| manufacturer-agent-...4jkwx | 1/1 | Running | 0 | ~3m(新) |
| manufacturer-agent-...db8fr | 1/1 | Running | 2 | ~5h(原有) |
| manufacturer-agent-...s6567 | 1/1 | Running | 0 | ~5m(新) |

3 個 pod 全部 1/1 Running,無 crash。

## 注意事項

- demo 期間 metrics-server 的 kubelet scrape 持續間歇性超時(舊有 `FailedGetResourceMetric` warning),但 HPA 機制在指標可讀時仍正確觸發 1→2 與 2→3。
- 此為**非正式** demo 執行(非 30-min soak 重跑),load 為 3 min history GET,目的僅驗證 HPA rescale 機制。

## 還原程序(Step 6)

demo 完成後,必須:
1. `kubectl delete hpa -n thesis manufacturer-agent-demo`
2. `kubectl apply -n thesis -f k8s_v2/hpa/hpa.yaml`(還原 Profile A + customer-agent + manufacturer-client HPA)
3. `kubectl scale deployment/manufacturer-agent -n thesis --replicas=3`
4. 確認 `kubectl get hpa,pods -n thesis`
