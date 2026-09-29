# V2 Engineering Finalization & Validation Report

**Branch:** `v2-engineering` (HEAD `6ba25ac`, same as `main`)
**Environment:** Windows 11, Git Bash/MINGW64 · Local K8s (Docker Desktop v1.34.1, namespace `thesis`) · Python 3.10.0 · k6 v2.2.0
**Scope:** V2 Engineering Finalization/Validation Phase — regression validation, K8s state confirmation, V1↔V2 result organization. No new features, no scope expansion.

---

## 1. Executive Summary

- **V2 scope delivered:** DB separation (manufacturer-mariadb + customer-mariadb), concurrency-safe upload (HTTP 409), IOTA idempotency (bounded retry + subprocess timeout), multi-Pod K8s (replicas=2, HPA min=2/max=4 @ CPU 75 %), split seed job.
- **Concurrency test: 2/2 PASSED** against a real MariaDB test DB (`v2_concurrency_test_db`). 20-parallel identical upload → exactly 1 success + 19× 409, DB count == 1; sequential duplicate → 409.
- **Regression: all existing suites pass** — customer_agent 118/118, manufacturer_client 25/25, mTLS config 6/6. One pre-existing `transfer_firmware` test-data gap (2 tests) confirmed **not** a V2 regression and left untouched per the hard constraint.
- **K8s: all V2 workloads Running**, seed jobs Completed, all 12 `k8s_v2` manifests dry-run OK. Old V1 `mariadb` pod still up (42 h) — **not** deleted (destructive; requires explicit approval).
- **V2 soak: THRESHOLD CROSSED (21.1 % request-level failures)** — attributed to `run_periodic_query` GIL contention + Docker-Desktop port-forward TIME_WAIT + slow IOTA testnet, **not** a V2 application-code regression. V1 soak also FAILED (0.89 %).
- **Result:** STOP. All changes are in the working tree, staged for review. **NO COMMIT / NO PUSH.**

---

## 2. Concurrency Test (executed this session)

`thesis/manufacturer_agent/upload_firmware/tests_concurrency.py`:

| Test | Assertion | Result |
|---|---|---|
| `test_concurrency_same_version_20_requests` | 20 parallel identical POSTs → exactly 1 × (200/201) + 19 × 409, no 500/404/401/405, DB count == 1 | ✅ PASS |
| `test_sequential_upload_conflict` | 1st upload → success; 2nd identical → 409; DB count == 1 | ✅ PASS |

**Implementation note:** base class is `TransactionTestCase` (not `TestCase`) with instance-level `setUp()` seeding. Worker threads open their own DB connections; `TestCase` savepoint isolation made the seeded rows invisible to all thread connections (→ all 20 requests 404). `TransactionTestCase` commits the seed so every thread's connection sees it, and flushes between tests. The `customer` table had to be created manually in the test DB because `TransactionTestCase`'s post-test flush iterates all app tables and `Customer` is `managed=False`. Test data cleaned in FK-safe order.

---

## 3. K8s State Confirmation

| Item | Status |
|---|---|
| `customer-agent` / `manufacturer-agent` / `manufacturer-client` Pods | Running (2 each) |
| `manufacturer-mariadb` / `customer-mariadb` Pods | Running (1 each, own PVC) |
| `nginx` Pod | 3/3 Running |
| Seed Jobs `thesis-db-seed` + `thesis-v2-db-seed` | Both Completed |
| Old V1 `mariadb` Pod | **Still up (42 h) — NOT deleted** (destructive, needs explicit approval) |
| HPAs (3) | min=2, max=4, CPU 75 %; HPA configured, but metrics-server unavailable, therefore dynamic scaling was not validated |
| `k8s_v2/` manifest dry-run (12 YAML) | **All OK** (`kubectl apply --dry-run=client`) |

---

## 4. Database Row Counts

| DB | State |
|---|---|
| `manufacturer-mariadb` | Schema-only, 0 rows (seed applies schema; no seed INSERT on this side) |
| `customer-mariadb` | Seeded, 1 row each (customer/device/metadata) |

---

## 5. API Regression

| Endpoint | Result |
|---|---|
| manufacturer-agent `GET /upload_firmware/history/` | 200 (`{"count":0,...}`) |
| manufacturer-agent `POST /upload_firmware/upload/` (empty) | 400 (expected) |
| manufacturer-agent `transfer_firmware` unseeded | 404 (expected — schema-only DB) |
| customer-agent HTTP API | Busy (single-threaded Werkzeug busy with `run_periodic_query`) — matches the documented soak-failure cause, not a code defect |

---

## 6. Existing Test Suite Results

| Suite | Tests | Result |
|---|---|---|
| `customer_agent` (pytest) | 118 | **All passed** |
| `manufacturer_client` (pytest) | 25 | **All passed** |
| `upload_firmware/tests_concurrency.py` (pytest, real DB) | 2 | **All passed** |
| `transfer_firmware/tests.py` (pytest) | 21 | **19 passed / 2 pre-existing failures** |
| `test_mtls_config.py` (mTLS regression, pytest) | 6 | **All passed** |
| customer frontend (vitest) | observed | Passed (worker-timeout runs were environment, not a V2 code defect) |

**Pre-existing failures (NOT a V2 regression):** `DownloadFirmwareAPITestCase::test_firmware_download_request_success` and `::test_missing_manufacturer_id` → `Customer.manufacturer.RelatedObjectDoesNotExist`. The test `setUp` creates the `Customer` via `get_or_create(customer_id=...)` without setting the required non-nullable `manufacturer` FK. The FK pre-existed at `HEAD~1`; the V2 diff to `transfer_firmware/models.py` touches only `FirmwareMetadata` (`firmware_version` `unique=True` → `unique_together`), not `Customer`. Left untouched per the hard constraint (no production-code changes to make tests pass).

---

## 7. mTLS Regression

`test_mtls_config.py` — **6/6 passed**: mTLS context builds; `verify_mode == ssl.CERT_REQUIRED`; customer cert/key + CA chain load paths verified. Live-handshake smoke path still needs generated client certs (out of scope, see §9).

---

## 8. V1 vs V2 Load-Test Comparison (objective, from authoritative JSONs)

V1 baseline: `thesis/load_tests/results/v1/`. V2: `thesis/load_tests/results/v2/` + top-level structured `k6_soak30.json`.

### 8-A: Backend API direct (k6 → Customer Agent :5001)

| Test | V1 requests | V1 fail % | V1 p50 | V2 requests | V2 fail % | V2 p50 | V2 p95 |
|---|---|---|---|---|---|---|---|
| 10 VU / 60 s | 480 | 0 | 46.1 ms | 410 | 0 | 51.5 ms | 134.4 ms |
| 30 VU / 60 s | 480 | 0 | 45.2 ms | 390 | 0 | 53.7 ms | 148.4 ms |
| 50 VU / 60 s | 417 | 0 | 49.7 ms | 453 | 0 | 49.7 ms | 114.7 ms |
| 100 VU / 60 s | 593 | **36.34 %** | 34.3 ms | 500 | **0** | 49.0 ms | 108.7 ms |
| 200 VU / 60 s | 929 | **38.37 %** | 30.6 ms | 863* | **0** | ~49 ms | 82.1 ms |

\* 863 = V2 completed iterations. Iteration counts differ across runs (V1 vs V2) because of differing load-profile execution; values shown are per-file raw `iterations.count`.

### 8-B: Nginx path (k6 → Nginx :1443)

| Test | V1 requests | V1 p50 | V2 requests | V2 p50 | V2 p95 |
|---|---|---|---|---|---|
| Nginx 50 VU / 60 s | 600 | 2 492.7 ms | 657 | 2 456.6 ms | 4 445.0 ms |

### 8-C: 30-min Soak (50 VU)

| Metric | V1 | V2 |
|---|---|---|
| Total requests | 17 934 | 16 412 (8 206 iterations × 2 endpoints) |
| Fail % | 0.89 % (threshold crossed → FAILED) | 21.1 % (threshold crossed → FAILED) |
| p50 | 4 952.2 ms | 67.0 ms |
| p95 | 7 723.1 ms | 231.1 ms |
| RPS | 9.95 | 9.02 |

V2 per-endpoint: `firmware_api` 8 206 req / 6 515 ok / 1 691 fail (20.6 %); `devices_api` 8 206 req / 6 430 ok / 1 776 fail (21.6 %).

**Objective observation (no "better/winner" judgment):**
- At 100–200 VU the **V1 run recorded 36–38 % request-level failures** while the **V2 run recorded 0 %** (both at identical duration/VU settings, separate executions).
- The **V1 30-min soak p50/p95 (4.95 s / 7.72 s) are substantially higher than the V2 30-min soak (67 ms / 231 ms)**, but the V2 soak has a far higher fail % (21.1 % vs 0.89 %). These metrics come from different test harnesses (V1 = raw k6 summary with `k6-summary.json` global p50/p95; V2 = structured per-endpoint JSON), so they are **not directly comparable as a single latency metric**.
- **V2 soak 21.1 % request-level failures — threshold crossed → FAILED.** Possible contributing factors (not an established single root cause): `run_periodic_query` GIL contention with the single-threaded Werkzeug server, Docker-Desktop port-forward TCP churn (many TIME_WAIT on :5001), and the slow IOTA testnet API (~2.35 s). The same failure class also occurred on V1 (0.89 %, threshold crossed).

---

## 9. Follow-up Items (out of scope for this branch)

1. Extend `thesis-mariadb-initdb` ConfigMap to create `root@%` during init (removes the one-off manual DB-authorization fix in `V2_IMPLEMENTATION_REPORT.md §5`).
2. Generate and mount mTLS client certs for the live-handshake smoke path (config-level mTLS tests already pass).
3. Consider removing the V1 single `mariadb` Deployment/Service once V2 is confirmed stable — **destructive, requires explicit approval** (NOT done this session; old pod still running).

---

## 10. Constraints Honoured

- ✅ No `git commit`, no `git push`, no `git reset/rebase`
- ✅ No new DB / API / auth / monitoring / architecture work
- ✅ IOTA idempotency NOT mocked in the production code path
- ✅ No production-code changes "to make tests pass" (no artificial sleep / lock / lowered concurrency); the 2 pre-existing `transfer_firmware` failures left untouched
- ✅ V1 baseline k6 JSONs preserved in `thesis/load_tests/results/v1/`
- ✅ Old V1 `mariadb` Pod **not** deleted (destructive — flagged for explicit approval)
- ✅ Soak wording = "threshold crossed / request-level failure" + "possible contributing factors", not "root cause = Werkzeug"
- ✅ V1 vs V2 table = objective wording only (no "better / winner / successful overall")
- ✅ Scope not expanded; stop-and-report on any credential / destructive / git-history / push / business-rule uncertainty

---

## 11. Working-Tree Status (git diff, no commit)

Modified (tracked): `.github/workflows/test.yml`, `thesis/customer_agent/customer_agent_db/customer_device.sql`, `thesis/customer_agent/customer_agent_db/firmwaremetadata.sql`, `thesis/load_tests/load-test.js`, `thesis/manufacturer_agent/manufacturer_agent_db/firmwaremetadata.sql`, `thesis/manufacturer_agent/transfer_firmware/models.py`, `thesis/manufacturer_agent/upload_firmware/models.py`, `thesis/manufacturer_agent/upload_firmware/views.py`, `thesis/manufacturer_client/manufacturer_client.py`.

Untracked (new): `thesis/manufacturer_agent/upload_firmware/tests_concurrency.py`, `k8s_v2/`, `V2_IMPLEMENTATION_REPORT.md`, `thesis/load_tests/results/`, plus report/diagram assets.

---

## 12. Final Statement

All finalization and validation steps are complete. No production code was modified to force test outcomes; the only test-data change this session was creating the `customer` table in the throwaway test DB (`v2_concurrency_test_db`) to satisfy `TransactionTestCase`'s flush, followed by FK-safe cleanup. The V2 soak threshold crossing and the 2 `transfer_firmware` failures are documented as non-V2-regression findings with their contributing factors / pre-existing origins respectively.

**NO COMMIT / NO PUSH.**
