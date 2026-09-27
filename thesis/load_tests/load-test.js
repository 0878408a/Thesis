// ============================================================================
// Thesis Phase 1: Customer API Load Test (k6)
//
// 測試目標 (唯讀, 只測 Backend API, 不經 Nginx/Frontend):
//   k6 → Customer Agent https://localhost:5001 → MariaDB
//
//   GET /api/customer/<CUSTOMER_ID>/firmware
//   GET /api/customer/<CUSTOMER_ID>/devices
//
// 本階段不包含: IOTA / Manufacturer Upload / Manufacturer Client /
// Nginx / mTLS / Query Pipeline / Telegram / ESP32 / Frontend
//
// 使用 (以 CLI flags 控制 VU / 時長; 見下方場景對照表):
//   # Smoke: 1 VU / 10s
//   k6 run load-test.js --vus 1 --duration 10s
//
//   # Load (分四次跑, 每次 60s):
//   k6 run load-test.js --vus 10  --duration 60s
//   k6 run load-test.js --vus 30  --duration 60s
//   k6 run load-test.js --vus 50  --duration 60s
//   k6 run load-test.js --vus 100 --duration 60s
//
//   # Stress (分五次跑, 每次 60s):
//   k6 run load-test.js --vus 10  --duration 60s
//   k6 run load-test.js --vus 30  --duration 60s
//   k6 run load-test.js --vus 50  --duration 60s
//   k6 run load-test.js --vus 100 --duration 60s
//   k6 run load-test.js --vus 200 --duration 60s
//
//   # Soak (本階段不執行; 需時 30 min):
//   k6 run load-test.js --vus 50 --duration 30m
//
//   可用 -e CUSTOMER_ID=xxx / -e CUSTOMER_URL=xxx 覆蓋預設值。
//
// 結果輸出: 每次執行結束後 handleSummary() 會依 API 分別列出
//   Requests / Success Rate / Error Rate / RPS / p50 / p95 / p99
//
// 環境: k6 v2 (winget GrafanaLabs.k6), C:/Program Files/k6/k6.exe
// ============================================================================
import http from 'k6/http';
import { check } from 'k6';
import { Trend, Counter } from 'k6/metrics';

// ---- env vars (via -e or defaults) ----
const CUSTOMER_URL = __ENV.CUSTOMER_URL || 'https://localhost:5001';
const CUSTOMER_ID  = __ENV.CUSTOMER_ID  || '3e01e6a7-1c25-4a5e-97c5-92ec5abfd10c';

// ---- custom metrics: 分別量測兩個 API ----
const firmwareApiDuration = new Trend('firmware_api_duration', false, 'ms');
const devicesApiDuration  = new Trend('devices_api_duration',  false, 'ms');
const firmwareApiErrors   = new Counter('firmware_api_errors');
const devicesApiErrors    = new Counter('devices_api_errors');

// ============================================================================
// 主執行路徑: 兩 API 各測一次, 無 sleep (讓 VU 全速跑, 看真實極限)
// k6: 匯出的 function 皆為 execution functions; 預設使用第一個匯出的
// ============================================================================
export function run() {
  doFirmware();
  doDevices();
}
export { run as default };

function doFirmware() {
  const resp = http.get(`${CUSTOMER_URL}/api/customer/${CUSTOMER_ID}/firmware`, {
    tags: { endpoint: 'customer_firmware' },
    tls: { insecureSkipTLSVerify: true }, // Docker 自簽憑證
    timeout: '10s',
  });
  let jsonValid = false;
  let statusOk = false;
  let ctypeOk = false;
  const passed = check(resp, {
    'firmware status 200': (r) => {
      statusOk = r.status === 200;
      return statusOk;
    },
    'firmware content-type json': (r) => {
      ctypeOk = (r.headers['Content-Type'] || '').includes('application/json');
      return ctypeOk;
    },
    'firmware valid json': (r) => {
      if (r.status !== 200) return false;
      try {
        const j = JSON.parse(
          r.body,
          _ => {},
          (k, v) => (k === 'firmwares' ? Array.from(v, (x) => x) : v)
        );
        jsonValid = j.customer_id === CUSTOMER_ID && Array.isArray(j.firmwares);
        return jsonValid;
      } catch {
        return false;
      }
    },
  });
  const ok = passed > 0 && statusOk && ctypeOk && jsonValid;
  firmwareApiDuration.add(resp.timings.duration);
  if (!ok) firmwareApiErrors.add(1);
  return ok;
}

function doDevices() {
  const resp = http.get(`${CUSTOMER_URL}/api/customer/${CUSTOMER_ID}/devices`, {
    tags: { endpoint: 'customer_devices' },
    tls: { insecureSkipTLSVerify: true },
    timeout: '10s',
  });
  let jsonValid = false;
  let statusOk = false;
  let ctypeOk = false;
  const passed = check(resp, {
    'devices status 200': (r) => {
      statusOk = r.status === 200;
      return statusOk;
    },
    'devices content-type json': (r) => {
      ctypeOk = (r.headers['Content-Type'] || '').includes('application/json');
      return ctypeOk;
    },
    'devices valid json': (r) => {
      if (r.status !== 200) return false;
      try {
        const j = JSON.parse(
          r.body,
          _ => {},
          (k, v) => (k === 'devices' ? Array.from(v, (x) => x) : v)
        );
        jsonValid = j.customer_id === CUSTOMER_ID && Array.isArray(j.devices);
        return jsonValid;
      } catch {
        return false;
      }
    },
  });
  const ok = passed > 0 && statusOk && ctypeOk && jsonValid;
  devicesApiDuration.add(resp.timings.duration);
  if (!ok) devicesApiErrors.add(1);
  return ok;
}

// ============================================================================
// thresholds: 觀察指標 (不硬寫死 p95 固定門檻; 僅標出 error 異常)
// ============================================================================
export const options = {
  insecureSkipTLSVerify: true, // Docker 自簽憑證, 全域跳過 TLS 驗證
  thresholds: {
    'http_req_failed{endpoint:customer_firmware}': ['rate<0.05'],
    'http_req_failed{endpoint:customer_devices}':  ['rate<0.05'],
  },
};

// ============================================================================
// handleSummary: 依 API 分別輸出
//   Requests / Success Rate / Error Rate / RPS / p50 / p95 / p99
// ============================================================================
function fmtPct(x) {
  return (x * 100).toFixed(2) + '%';
}
function fmtMs(x) {
  return Number.isFinite(x) ? x.toFixed(1) + ' ms' : 'n/a';
}
function num(x) {
  // 從 k6 metric values 取 number; 若無則回傳 null (CI JSON 不爆 undefined)
  return x === undefined || x === null ? null : x;
}

export function handleSummary(data) {
  const values = (metricName) =>
    (data.metrics[metricName] && data.metrics[metricName].values) || {};

  const fwErrCount = values('firmware_api_errors').value || 0;
  const dvErrCount = values('devices_api_errors').value || 0;

  const totalReqs = values('http_reqs').count || 0;
  const totalFail = values('http_req_failed').count || 0;
  const totalDur  = values('http_req_duration');
  const fwDur     = values('firmware_api_duration');
  const dvDur     = values('devices_api_duration');

  const totalRunTime = data.state.testRunDurationMs / 1000;
  // 每個 API 各佔約一半 request (兩 API 在同一 iteration 各跑一次)
  const fwReqs = Math.round(totalReqs / 2);
  const dvReqs = totalReqs - fwReqs;

  const apiBlock = (name, path, durV, errCount, estReqs) => {
    const success = Math.max(estReqs - (errCount || 0), 0);
    const errRate = estReqs > 0 ? (errCount || 0) / estReqs : 0;
    const rps = totalRunTime > 0 ? estReqs / totalRunTime : 0;
    return [
      '',
      name,
      `  ${path}`,
      '',
      `  Requests:     ${estReqs}`,
      `  Success:      ${success} (${estReqs > 0 ? (success / estReqs * 100).toFixed(2) : 0}%)`,
      `  Errors:       ${errCount || 0} (${fmtPct(errRate)})`,
      `  RPS:          ${rps.toFixed(2)}`,
      `  p50:          ${fmtMs(durV['med'])}`,
      `  p95:          ${fmtMs(durV['p(95)'])}`,
      `  p99:          ${fmtMs(durV['p(99)'])}`,
      '',
    ].join('\n');
  };

  const lines =
    '\n' +
    '='.repeat(62) +
    '\nPer-API Summary — Customer Agent API (Phase 1)\n' +
    '='.repeat(62) +
    apiBlock(
      'Customer Firmware API',
      'GET /api/customer/<id>/firmware',
      fwDur,
      fwErrCount,
      fwReqs
    ) +
    apiBlock(
      'Customer Devices API',
      'GET /api/customer/<id>/devices',
      dvDur,
      dvErrCount,
      dvReqs
    ) +
    '='.repeat(62) +
    '\nGlobal Summary\n' +
    '='.repeat(62) +
    `\n  Total requests:   ${totalReqs}\n` +
    `  Total non-2xx:      ${totalFail}\n` +
    `  Total RPS:          ${(totalRunTime > 0 ? totalReqs / totalRunTime : 0).toFixed(2)}\n` +
    `  p50 (all):          ${fmtMs(totalDur['med'])}\n` +
    `  p95 (all):          ${fmtMs(totalDur['p(95)'])}\n` +
    `  p99 (all):          ${fmtMs(totalDur['p(99)'])}\n` +
    '='.repeat(62) +
    '\n';

  // ---- 結構化 JSON 摘要 (供 CI artifact; 與 stdout 同步產生) ----
  // 寫入 K6_JSON_SUMMARY env 指定的檔名; 未設定則預設 'k6-summary.json'
  // handleSummary 回傳 object 可指定要寫入的檔案
  const jsonSummary = {
    target: {
      customer_url: CUSTOMER_URL,
      customer_id: CUSTOMER_ID,
    },
    duration_seconds: totalRunTime,
    per_api: {
      customer_firmware: {
        endpoint: 'GET /api/customer/<id>/firmware',
        requests: fwReqs,
        success: Math.max(fwReqs - (fwErrCount || 0), 0),
        errors: fwErrCount || 0,
        error_rate: fwReqs > 0 ? ((fwErrCount || 0) / fwReqs) : 0,
        rps: totalRunTime > 0 ? Math.round(fwReqs / totalRunTime * 100) / 100 : 0,
        p50_ms: num(fwDur['med']),
        p95_ms: num(fwDur['p(95)']),
        p99_ms: num(fwDur['p(99)']),
      },
      customer_devices: {
        endpoint: 'GET /api/customer/<id>/devices',
        requests: dvReqs,
        success: Math.max(dvReqs - (dvErrCount || 0), 0),
        errors: dvErrCount || 0,
        error_rate: dvReqs > 0 ? ((dvErrCount || 0) / dvReqs) : 0,
        rps: totalRunTime > 0 ? Math.round(dvReqs / totalRunTime * 100) / 100 : 0,
        p50_ms: num(dvDur['med']),
        p95_ms: num(dvDur['p(95)']),
        p99_ms: num(dvDur['p(99)']),
      },
    },
    global: {
      total_requests: totalReqs,
      total_non_2xx: totalFail,
      rps: totalRunTime > 0 ? Math.round(totalReqs / totalRunTime * 100) / 100 : 0,
      p50_ms: num(totalDur['med']),
      p95_ms: num(totalDur['p(95)']),
      p99_ms: num(totalDur['p(99)']),
    },
  };

  const jsonOut = __ENV.K6_JSON_SUMMARY || 'k6-summary.json';
  return {
    stdout: lines,
    [jsonOut]: JSON.stringify(jsonSummary, null, 2),
  };
}
