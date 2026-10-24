// ============================================================================
// In-cluster Manufacturer Agent mTLS upload load test.
// Tests the POST /upload_firmware/upload/ endpoint under mTLS contract (202 Accepted).
// Generates unique version strings per VU iteration to avoid 409 Conflict.
// ============================================================================
import http from 'k6/http';
import { check } from 'k6';
import { Trend, Counter } from 'k6/metrics';

const URL = __ENV.MANUFACTURER_URL || 'https://nginx:8443';
const UPLOAD_PATH = '/manufacturer/agent/upload_firmware/upload/';

const uploadDuration = new Trend('manufacturer_upload_duration', true);
const status202 = new Counter('manufacturer_upload_202');
const status409 = new Counter('manufacturer_upload_409');
const statusOther = new Counter('manufacturer_upload_other_status');

export const options = {
  tlsAuth: [{
    cert: open('/certs/ecdsa_manufacturer_client_cert.pem'),
    key: open('/certs/ecdsa_manufacturer_private_key.pem'),
  }],
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};

// Base test payload (unsigned smoke/load check for endpoint handling)
export function run() {
  const uniqueVer = `k6_load_${__VU}_${__ITER}_${Date.now()}`;
  const payload = JSON.stringify({
    metadata: {
      firmware_version: uniqueVer,
      device_type: 'esp32',
      manufacturer_id: '123e4567-e89b-12d3-a456-426614174000',
      firmware_size: 16,
      release_date: Math.floor(Date.now() / 1000) + 2208988800, // NTP timestamp
      metadata_signature_algorithm: 'ecdsa-sha256',
      firmware_signature_algorithm: 'ecdsa-sha256',
      metadata_signature: 'dGVzdA==',
      firmware_signature: 'dGVzdA=='
    },
    firmware_data: 'dGVzdF9kYXRhXzEyMzQ1Ng=='
  });

  const res = http.post(URL + UPLOAD_PATH, payload, {
    headers: { 'Content-Type': 'application/json' },
    timeout: '20s',
    tags: { endpoint: 'manufacturer_upload' },
  });
  uploadDuration.add(res.timings.duration);

  if (res.status === 202) status202.add(1);
  else if (res.status === 409) status409.add(1);
  else statusOther.add(1);

  check(res, {
    'upload returned expected status (202 accepted, or 400/409 validation)': (r) => r.status === 202 || r.status === 400 || r.status === 409,
  });
}
export { run as default };

export function handleSummary(data) {
  const metric = data.metrics.manufacturer_upload_duration;
  const values = (name) => data.metrics[name]?.values || {};
  const counter = (name) => values(name).count || 0;
  const failed = values('http_req_failed');
  const checks = values('checks');
  const requestCount = data.metrics.http_reqs.values.count;
  return {
    stdout: [
      'Manufacturer Agent mTLS upload load summary',
      `requests=${requestCount}`,
      `rps=${data.metrics.http_reqs.values.rate.toFixed(2)}`,
      `http_req_failed=${((failed.rate || 0) * 100).toFixed(2)}%`,
      `status_202=${counter('manufacturer_upload_202')}`,
      `status_409=${counter('manufacturer_upload_409')}`,
      `status_other=${counter('manufacturer_upload_other_status')}`,
      `checks_passed=${checks.passes || 0}`,
      `checks_failed=${checks.fails || 0}`,
      `duration_ms min=${metric.values.min} p50=${metric.values.med} p90=${metric.values['p(90)']} p95=${metric.values['p(95)']} p99=${metric.values['p(99)']} max=${metric.values.max}`,
      '',
    ].join('\n'),
  };
}
