// ============================================================================
// In-cluster Manufacturer Agent mTLS history load test.
// The k6 pod mounts the existing manufacturer-client certificate secret and
// trusts the project's CA via SSL_CERT_FILE; no TLS verification is skipped.
import http from 'k6/http';
import { check } from 'k6';
import { Trend, Counter } from 'k6/metrics';

const URL = __ENV.MANUFACTURER_URL || 'https://nginx:8443';
const HISTORY_PATH = '/manufacturer/agent/upload_firmware/history/';

const historyDuration = new Trend('manufacturer_history_duration', true);
const status2xx = new Counter('manufacturer_history_2xx');
const status4xx = new Counter('manufacturer_history_4xx');
const status5xx = new Counter('manufacturer_history_5xx');
const statusOther = new Counter('manufacturer_history_other_status');
const invalidBodies = new Counter('manufacturer_history_invalid_body');

export const options = {
  tlsAuth: [{
    cert: open('/certs/ecdsa_manufacturer_client_cert.pem'),
    key: open('/certs/ecdsa_manufacturer_private_key.pem'),
  }],
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};

export function run() {
  const res = http.get(URL + HISTORY_PATH, {
    timeout: '20s',
    tags: { endpoint: 'manufacturer_history' },
  });
  historyDuration.add(res.timings.duration);

  if (res.status >= 200 && res.status < 300) status2xx.add(1);
  else if (res.status >= 400 && res.status < 500) status4xx.add(1);
  else if (res.status >= 500 && res.status < 600) status5xx.add(1);
  else statusOther.add(1);

  let validBody = false;
  try {
    const body = res.json();
    validBody = typeof body.count === 'number' && Array.isArray(body.results);
  } catch (_) {
    validBody = false;
  }
  if (!validBody) invalidBodies.add(1);

  check(res, {
    'history status 200': (r) => r.status === 200,
    'history body has count/results': () => validBody,
  });
}
export { run as default };

export function handleSummary(data) {
  const metric = data.metrics.manufacturer_history_duration;
  const values = (name) => data.metrics[name]?.values || {};
  const counter = (name) => values(name).count || 0;
  const failed = values('http_req_failed');
  const checks = values('checks');
  const requestCount = data.metrics.http_reqs.values.count;
  const failureCount = Math.round((failed.rate || 0) * requestCount);
  return {
    stdout: [
      'Manufacturer Agent mTLS history load summary',
      `requests=${requestCount}`,
      `rps=${data.metrics.http_reqs.values.rate.toFixed(2)}`,
      `http_req_failed=${((failed.rate || 0) * 100).toFixed(2)}% (${failureCount}/${requestCount})`,
      `status_2xx=${counter('manufacturer_history_2xx')}`,
      `status_4xx=${counter('manufacturer_history_4xx')}`,
      `status_5xx=${counter('manufacturer_history_5xx')}`,
      `status_other=${counter('manufacturer_history_other_status')}`,
      `invalid_bodies=${counter('manufacturer_history_invalid_body')}`,
      `checks_passed=${checks.passes || 0}`,
      `checks_failed=${checks.fails || 0}`,
      `duration_ms min=${metric.values.min} p50=${metric.values.med} p90=${metric.values['p(90)']} p95=${metric.values['p(95)']} p99=${metric.values['p(99)']} max=${metric.values.max}`,
      '',
    ].join('\n'),
  };
}
