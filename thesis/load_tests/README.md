# Load Testing Directory Structure & Test Suite

This directory contains the performance, concurrency, and soak testing suite for the Thesis system.

## Directory Structure

```text
thesis/load_tests/
├── scripts/
│   ├── manufacturer-upload-test.js     # Upload API mTLS load test
│   ├── manufacturer-history-test.js    # History API mTLS load test (Read bottleneck isolation)
│   ├── manufacturer-soak-test.js       # 30-minute soak test script
│   └── load-test.js                    # Customer Agent k6 test
│
├── results/
│   ├── latest/
│   │   ├── short/                      # Short runs (10, 50, 100 VU)
│   │   └── soak/                       # 30-minute soak test outputs
│   │
│   └── archive/
│       ├── before/                     # Werkzeug single-worker baseline (10, 50, 100 VU)
│       ├── phase1/                     # Gunicorn 2-worker baseline (10, 50, 100 VU)
│       └── phase2/                     # Async IOTA worker + 30-min soak failure baseline
│
└── README.md
```

## Running Tests

All official performance tests execute **inside the Kubernetes cluster** via the `manufacturer-k6` pod, routing through **internal Nginx (`https://nginx:8443`)** with valid **mTLS client certificates**. No port-forward is used for official benchmark numbers.

Example execution:
```bash
kubectl exec -n thesis manufacturer-k6 -- k6 run --vus 10 --duration 2m /scripts/manufacturer-history-test.js
```

