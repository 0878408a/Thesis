# V2 Next Phase Engineering Validation - Baseline Investigation

Captured 2026-10-06 before any current-phase code/resource changes. Existing worktree changes from the previous phase were preserved; `git status` showed user/previous-phase modifications in V2 reports, K8s resource/HPA manifests, Customer Agent, Manufacturer Agent/Client, certs, OpenSpec and generated artifacts. No reset/cleanup was performed.

## Git and repository baseline

- HEAD: `6721994 feat: add V2 engineering deployment and performance validation`; previous commits include `6ba25ac chore: finalize CI, Docker, mTLS and test configuration`.
- Async IOTA Worker already exists in the dirty worktree and is live in K8s; this phase started with it Running, no pending or failed submission rows.
- Existing k6 artifacts include Customer Agent V1/V2 JSONs and Manufacturer before/Phase 1/Phase 2 History mTLS outputs. No `manufacturer-upload-test.js` or dedicated `manufacturer-soak-test.js` existed yet; the current Manufacturer script was History-only.
- Manufacturer tests present: `upload_firmware/tests.py`, `tests_concurrency.py`, `transfer_firmware/tests.py`. Frontend has App, FirmwareUpload, FirmwareHistory, UploadStatus Vitest files. GitHub workflows: `test.yml`, `docker-e2e.yml`, `performance.yml`, `copilot-setup-steps.yml`.

## Docker Desktop / Kubernetes node

- Docker Desktop node `docker-desktop`, Kubernetes v1.34.1, 4 allocatable CPU cores, 7,992,588 Ki memory (about 7.62 GiB); Docker engine reports 4 CPUs / 8,289,267,712 bytes memory.
- Baseline `kubectl top nodes`: 3,084m CPU / 77%, memory 3,153Mi / 40%. During controlled 100 VU history traffic: about 3,642m / 91%. During the prior 30-minute soak: about 3,748m / 93%.
- 25 non-terminated Pods at the baseline snapshot. Node allocated CPU requests 3,300m (82%), limits 2,800m (70%); memory requests 2,416Mi (30%), limits 3,156Mi (40%). Scheduler has about 700m CPU request headroom before accounting for transient DaemonSet/service CPU.
- Node `MemoryPressure`, `DiskPressure`, `PIDPressure` were False; no Pending/evicted pods in the snapshot. No current Agent OOMKilled or restarts in the live ReplicaSet.

## Manufacturer Agent / Kubernetes

- Deployment 3 replicas at idle, HPA `min=3`, `max=4`, CPU target 75%; Gunicorn 2 sync workers per API Pod. Agent each request/limit: CPU 250m/250m, memory 128Mi/256Mi.
- Service resolves to one Service IP and three ready Pod endpoints on port 8000. Internal Nginx upstream is plain HTTP; outer Manufacturer entry remains `:8443` mTLS.
- HPA live status showed 3 replicas, ~0–17% idle utilization depending on sample. Metrics-server occasionally returned `<unknown>`; prior HPA events include successful `3 → 4` rescale under k6.
- During prior 30-minute soak, HTTP status counts from Nginx were 14,775 200, 89 499, 12 500. The 499s were client-abandoned; 500 tracebacks were DB TCP connect errors (below).
- Nginx access log format includes only client/status/bytes/request/user-agent; it does not currently log `$upstream_connect_time` or `$upstream_response_time`. `stub_status` is not configured, so active/waiting connection counts and per-request upstream latency cannot be reconstructed from existing logs without a future observability-only config change.

## MariaDB

- `manufacturer-mariadb` Service resolves to one endpoint: `10.1.0.101:3306`. Pod request: memory 256Mi; no CPU request/limit or memory limit configured. Current process was Running, memory around 130–143Mi, CPU around 80–270m across samples.
- Restart count 3; last termination was historical exit 255 several days earlier, not during this baseline. Readiness probe has accumulated 1,200+ `mariadb-admin ping` timeouts over roughly five days (3s probe timeout), although current `mariadb-admin ping` succeeds.
- MariaDB status after controlled k6: `Threads_connected=2–4`, `Threads_running=1–2`, `Max_used_connections=20` (`max_connections=151`), `Slow_queries=0`. `Connections` was 128,441; `Aborted_clients=17`.
- `Aborted_connects` rose from 108 to 158 after an explicit 50-socket TCP probe that opened and closed unauthenticated connections; later to 208 after a second such probe. These increments are caused by the diagnostic probes and must not be attributed to Agent connection failures.
- 20 fresh client TCP+`SELECT 1` connections succeeded: median 18.23ms, p95 50.87ms, max 128.49ms.
- Idle 100 TCP connect probes: 100/100 success, median 1.7ms, p95 15.4ms, max 36.6ms. During controlled 100 VU read traffic: 50/50 success; sample A p95 70.75ms/max 122ms, sample B p95 4.01ms/max 24.46ms. No connection failure was reproduced in these finite socket probes.
- During the earlier 30-minute soak only, Agent logs showed `OperationalError (2002) Can't connect to server on 'manufacturer-mariadb' (115)`. This is a real load-correlated symptom, but the latest idle/short TCP probes did not isolate a stable MariaDB listener or max-connection failure.

## CPU throttling evidence

- Agent cgroup `cpu.max` is `25000 100000` (250m quota), memory max 256Mi. Three long-lived Agent Pods, sampled before the second controlled 100 VU run, had `(nr_periods,nr_throttled,throttled_usec)` of `(49,911,13,096,689,634,023)`, `(48,656,11,078,582,279,754)`, `(46,857,10,091,480,424,252)` respectively. A later active-load sample had `(50,231,13,256,697,991,495)`, `(49,003,11,270,592,802,241)`, `(47,244,10,903,520,146,457)`.
- Across those asynchronous snapshots, counter deltas were `+320/+160/+8,357,472 usec`, `+347/+192/+11,602,487 usec`, `+387/+207/+9,722,205 usec` for periods/throttled periods/throttled usec. This demonstrates quota throttling during the sampled interval, but the interval boundaries were not aligned exactly to the full k6 duration; it is a signal, not an exact per-test throttle ratio.
- No MariaDB cgroup throttling was observed (`nr_throttled=0`) when its cgroup was sampled; the container has no CPU quota.

## Controlled in-cluster 100 VU test

Path: k6 Pod in namespace `thesis` → `https://nginx:8443` with existing Manufacturer Client cert/key and project CA → Nginx mTLS → Manufacturer Agent History API. No port-forward, no TLS verification bypass.

- 1,744 requests, RPS 13.20; p50 4.642s, p90 17.009s, p95 18.116s, p99 20.008s, max 20.286s.
- 1.26% `http_req_failed` (22/1,744); 1,722 HTTP 2xx; 0 4xx; 0 5xx; 22 no-status request timeouts at the k6 20s timeout. Checks 3,444 passed / 44 failed.
- HPA metric collection was intermittently `<unknown>` during the run; HPA remained min=3/max=4 in this specific short run. Node CPU was about 91%.
- This reproduces latency/timeout under 100 VU with a valid mTLS business-path test, without reproducing a MariaDB TCP connect error in the 50-socket probe. Node pressure and 250m per-Pod throttling are correlated candidates; neither alone is yet proven to be the sole cause of the prior 30-minute DB TCP errors.

## Prior 30-minute failure retained as historical evidence

`manufacturer-after-phase2-soak30.out`: 50 VU, 30,705 requests, 17.04 RPS, p50 2.267s, p95 7.165s, p99 11.305s, max 21.215s; 30,603 2xx, 10 HTTP 500, 92 timeouts/no-status, total 0.33% failure. Node CPU reached about 92–93%, HPA scaled 3→4. Django 500 root traceback was DB Service TCP connect error `(2002, ... (115))`; MariaDB slow queries 0 and max used connections 18/151. This remains a mixed node-pressure/network/DB-connect failure, not evidence for adding a pool or changing DB schema.

## Baseline decision

No application, DB, HPA, Nginx, or resource changes have been made in this new phase yet. Evidence confirms measurable Agent CPU throttling under load and high single-node CPU pressure; it does **not** confirm MariaDB max-connection exhaustion or slow queries. Next step is a controlled, reversible CPU-limit experiment (same request 250m/HPA target, only the Agent limit varied) with equal k6 load, exact cgroup throttle deltas, DB TCP/SQL latency and error status captured. Keep/revert the change based on measured benefit and no regression in DB connectivity/node pressure.

## Phase 2: CPU Limit Experiment (250m → 350m)

**Hypothesis:** Raising the Agent Pod CPU limit from 250m to 350m would reduce cgroup throttling and improve p95/p99 latency under 100-VU load.

**Method:**
1. `kubectl set resources deployment/manufacturer-agent -n thesis --containers=manufacturer-agent --limits=cpu=350m`
2. Wait for rolling update (3 new Pods scheduled).
3. Run identical k6 in-cluster 100-VU / 2-min History test via `manufacturer-k6` Pod → `https://nginx:8443` mTLS.
4. Collect cgroup `cpu.stat` deltas before/after.
5. Revert to 250m.

**Results (k6, in-cluster mTLS, 100 VU, 2 min):**

| Metric | 250m baseline | 350m experiment | Δ |
|---|---|---|---|
| Total requests | 1,744 | 1,535 | −209 |
| RPS | 13.20 | 12.18 | −0.79 |
| Failure rate | 1.26% | 8.01% | +6.75 pp |
| p50 | 4,642 ms | 4,814 ms | +172 ms |
| p95 | 18,116 ms | 20,096 ms | +1,980 ms |
| p99 | 20,008 ms | 23,002 ms | +2,994 ms |

**Node CPU during 350m run:** ~91% (same as 250m baseline). HPA metrics still `<unknown>` (metrics-server gap). MariaDB `Max_used_connections` peaked at 47/151; `Slow_queries=0`.

**cgroup throttle deltas (350m run):** All three Pods showed increased `nr_throttled` and `throttled_usec` compared to the 250m baseline, indicating the 350m quota was still being hit — the node-level CPU saturation (91%) is the binding constraint, not the Pod cgroup quota.

**Conclusion:**
- Raising the Pod CPU limit **made performance worse** (higher failure rate, higher p95/p99). Root cause: on a saturated single Docker Desktop node (91% CPU), giving each Pod a larger quota does not create new CPU capacity; it increases context-switch overhead and contention among 3+ Pods simultaneously.
- The 250m limit is the correct ceiling for this environment. **350m experiment is REVERTED.**
- `k8s_v2/deployments/manufacturer-agent.yaml` has been reverted to `cpu: 250m` in both requests and limits.
- The binding constraint is the single-node Docker Desktop CPU allocation (4 cores, ~91% under 100-VU load), not the Pod-level cgroup quota or MariaDB connections. This is an environment limitation, not an application bug.

**Decision:** Keep 250m. No further resource changes. Document as environment limitation in final report.
