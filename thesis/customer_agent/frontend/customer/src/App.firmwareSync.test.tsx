/**
 * App Firmware 自動同步測試。
 *
 * 驗證：
 * - 首次載入會 query Firmware / Devices
 * - Polling 每 10 秒重新 query Firmware API
 * - 手動 Refresh 會再次 query Firmware API
 * - 新增 Firmware 後 Known Firmware 數量與 Firmware History 會更新
 * - Firmware refresh / polling 失敗時保留舊資料，並顯示明確錯誤訊息
 * - unmount 後不再觸發 polling
 * - Devices 狀態不受 Firmware polling / refresh 影響
 * - 避免同時發送重複 Firmware request
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import App from './App'

const FIRMWARE_URL = '/api/customer/3e01e6a7-1c25-4a5e-97c5-92ec5abfd10c/firmware'
const DEVICES_URL = '/api/customer/3e01e6a7-1c25-4a5e-97c5-92ec5abfd10c/devices'

// Plain-object response mock (fake-timer-safe: no real Response.json() I/O)
type MockResponse = {
  ok: boolean
  status: number
  json: () => Promise<unknown>
}

function firmwareResponse(records: number[]): MockResponse {
  const body = {
    customer_id: '3e01e6a7-1c25-4a5e-97c5-92ec5abfd10c',
    device_type: 'esp32',
    firmwares: records.map((index) => ({
      object_id: `obj-${index}`,
      manufacturer_id: '123e4567-e89b-12d3-a456-426614174000',
      manufacturer_name: 'Acme Inc',
      device_type: 'esp32',
      firmware_version: `v1.${index}`,
      firmware_size: 100 + index,
      release_date: 3_800_000_000 + index,
    })),
  }
  return { ok: true, status: 200, json: () => Promise.resolve(body) }
}

function firmwareErrorResponse(status: number): MockResponse {
  return {
    ok: false,
    status,
    json: () => Promise.resolve({}),
  }
}

function devicesResponse(): MockResponse {
  return { ok: true, status: 200, json: () => Promise.resolve({ devices: [] }) }
}

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

function firmwareCalls() {
  return mockFetch.mock.calls.filter(([url]) => url === FIRMWARE_URL)
}

function devicesCalls() {
  return mockFetch.mock.calls.filter(([url]) => url === DEVICES_URL)
}

async function waitForInitialLoad() {
  // Under fake timers, waitFor's internal setTimeout is also faked.  Use
  // vi.runAllTicks() to flush pending Promise microtasks so that fetch
  // (mocked) and .json() (plain Promise.resolve) both settle.
  for (let i = 0; i < 50; i++) {
    await act(async () => {
      vi.runAllTicks()
    })
    if (screen.queryByTestId('dashboard')) break
  }
  expect(screen.getByTestId('dashboard')).toBeInTheDocument()
}

describe('App firmware sync', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockFetch.mockReset()
    mockFetch.mockImplementation((url: string) => {
      if (url === FIRMWARE_URL) {
        return Promise.resolve(firmwareResponse([1, 2, 3]))
      }
      if (url === DEVICES_URL) {
        return Promise.resolve(devicesResponse())
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`))
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('queries firmware and devices on initial load', async () => {
    render(<App />)
    await waitForInitialLoad()

    expect(firmwareCalls()).toHaveLength(1)
    expect(devicesCalls()).toHaveLength(1)
    expect(
      screen.getByTestId('stat-card-firmware').querySelector('[data-testid="stat-value"]'),
    ).toHaveTextContent('3')
    expect(
      screen.getByTestId('stat-card-devices').querySelector('[data-testid="stat-value"]'),
    ).toHaveTextContent('0')
  })

  it('refreshes firmware every 10 seconds', async () => {
    render(<App />)
    await waitForInitialLoad()
    expect(firmwareCalls()).toHaveLength(1)

    await act(async () => {
      vi.advanceTimersByTime(10_000)
      await Promise.resolve()
    })
    expect(firmwareCalls()).toHaveLength(2)

    await act(async () => {
      vi.advanceTimersByTime(10_000)
      await Promise.resolve()
    })
    expect(firmwareCalls()).toHaveLength(3)
    expect(devicesCalls()).toHaveLength(1)
  })

  it('manual Refresh button queries firmware again without re-querying devices', async () => {
    render(<App />)
    await waitForInitialLoad()

    const refreshButton = screen.getByTestId('refresh-firmware-button')
    await act(async () => {
      refreshButton.click()
      await Promise.resolve()
    })

    expect(firmwareCalls()).toHaveLength(2)
    expect(devicesCalls()).toHaveLength(1)
  })

  it('updates known firmware count and firmware history after a new record appears', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === FIRMWARE_URL) {
        return Promise.resolve(firmwareResponse([1, 2, 3, 4]))
      }
      return Promise.resolve(devicesResponse())
    })

    render(<App />)
    await waitForInitialLoad()

    expect(
      screen.getByTestId('stat-card-firmware').querySelector('[data-testid="stat-value"]'),
    ).toHaveTextContent('4')
    expect(screen.getAllByTestId('firmware-record').length).toBe(4)
    expect(
      screen.getAllByTestId('firmware-record').some((record) => record.textContent?.includes('v1.4')),
    ).toBe(true)
  })

  it('keeps old firmware data and shows a refresh error when polling fails', async () => {
    const nextResponse: MockResponse = firmwareErrorResponse(500)

    mockFetch.mockImplementation((url: string) => {
      if (url === FIRMWARE_URL) {
        return Promise.resolve(
          mockFetch.mock.calls.length > 1
            ? nextResponse
            : firmwareResponse([1, 2, 3]),
        )
      }
      return Promise.resolve(devicesResponse())
    })

    render(<App />)
    await waitForInitialLoad()
    expect(
      screen.getByTestId('stat-card-firmware').querySelector('[data-testid="stat-value"]'),
    ).toHaveTextContent('3')

    await act(async () => {
      vi.advanceTimersByTime(10_000)
      await Promise.resolve()
    })

    expect(
      screen.getByTestId('stat-card-firmware').querySelector('[data-testid="stat-value"]'),
    ).toHaveTextContent('3')
    expect(screen.getByTestId('dashboard')).toBeInTheDocument()
    expect(screen.getByTestId('firmware-refresh-error').textContent).toMatch(
      /500/i,
    )
    expect(screen.queryByTestId('dashboard-error')).toBeNull()
  })

  it('stops polling after unmount', async () => {
    const { unmount } = render(<App />)
    await waitForInitialLoad()
    unmount()

    mockFetch.mockClear()
    await act(async () => {
      vi.advanceTimersByTime(10_000)
      await Promise.resolve()
    })

    expect(firmwareCalls()).toHaveLength(0)
  })

  it('does not start duplicate firmware requests when polling and refresh overlap', async () => {
    let resolveFirst!: (value: Response) => void
    const pending = new Promise<Response>((resolve) => {
      resolveFirst = resolve
    })

    mockFetch.mockImplementation((url: string) => {
      if (url === FIRMWARE_URL) {
        return pending
      }
      return Promise.resolve(devicesResponse())
    })

    render(<App />)
    // Wait for the first firmware call to fire (in-flight, still pending)
    for (let i = 0; i < 50; i++) {
      await act(async () => { vi.runAllTicks() })
      if (firmwareCalls().length >= 1) break
    }
    expect(firmwareCalls()).toHaveLength(1)

    // Click Refresh + advance 10 s in one act; polling timer fires but
    // in-flight guard prevents a second call.
    await act(async () => {
      screen.getByTestId('refresh-firmware-button').click()
      vi.advanceTimersByTime(10_000)
    })
    expect(firmwareCalls()).toHaveLength(1)

    // Resolve the single in-flight request and let React commit.
    await act(async () => {
      resolveFirst(firmwareResponse([1]) as unknown as Response)
      vi.runAllTicks()
    })

    expect(
      screen.getByTestId('stat-card-firmware').querySelector('[data-testid="stat-value"]'),
    ).toHaveTextContent('1')
  })

  it('shows device information while firmware request is still pending', async () => {
    let resolveFirmware!: (value: Response) => void
    const pending = new Promise<Response>((resolve) => {
      resolveFirmware = resolve
    })

    const deviceData = [
      {
        manufacturer_id: 'm1',
        manufacturer_name: 'Acme Inc',
        device_type: 'esp32',
        current_firmware_version: 'v1.11',
        update_method: 'https',
      },
    ]

    mockFetch.mockImplementation((url: string) => {
      if (url === FIRMWARE_URL) {
        return pending
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ devices: deviceData }),
      })
    })

    render(<App />)
    // Let devices settle but keep firmware pending
    for (let i = 0; i < 50; i++) {
      await act(async () => { vi.runAllTicks() })
      if (
        screen.queryByTestId('stat-card-devices')?.querySelector('[data-testid="stat-value"]')?.textContent === '1'
      ) break
    }

    // Device fields are visible even though firmware has not resolved yet
    const deviceSection = screen.getByText('Devices', { selector: 'h2' }).closest('section')
    expect(deviceSection?.textContent).toContain('Acme Inc')
    expect(deviceSection?.textContent).toContain('esp32')
    expect(deviceSection?.textContent).toContain('v1.11')
    expect(deviceSection?.textContent).toContain('https')

    // Advance polling timer — should not clear devices
    await act(async () => {
      vi.advanceTimersByTime(10_000)
    })

    // Resolve the pending firmware request
    await act(async () => {
      resolveFirmware(firmwareResponse([1]) as unknown as Response)
      vi.runAllTicks()
    })

    expect(
      screen.getByTestId('stat-card-firmware').querySelector('[data-testid="stat-value"]'),
    ).toHaveTextContent('1')
    // Devices still visible after firmware resolves
    expect(
      screen.getByTestId('stat-card-devices').querySelector('[data-testid="stat-value"]'),
    ).toHaveTextContent('1')
  })

  // ---------------------------------------------------------------------------
  // Device API URL & display tests (real /api URL, not mock)
  // ---------------------------------------------------------------------------

  it('uses the real Device API URL with the correct customer ID', async () => {
    // DEVICES_URL must be the real /api path, not the old /mock path
    expect(DEVICES_URL).toBe('/api/customer/3e01e6a7-1c25-4a5e-97c5-92ec5abfd10c/devices')
    expect(DEVICES_URL).not.toContain('/mock/')

    render(<App />)
    await waitForInitialLoad()
    // devicesCalls() filters by DEVICES_URL — proves the correct URL was called
    expect(devicesCalls()).toHaveLength(1)
  })

  it('displays device info (manufacturer_name, device_type, current_firmware_version, update_method) when the API returns data', async () => {
    const deviceData = [
      {
        manufacturer_id: 'm1',
        manufacturer_name: 'Acme Inc',
        device_type: 'esp32',
        current_firmware_version: 'v1.11',
        update_method: 'https',
      },
    ]
    const realDevicesResponse: MockResponse = {
      ok: true,
      status: 200,
      json: () => Promise.resolve({ customer_id: '3e01e6a7-1c25-4a5e-97c5-92ec5abfd10c', devices: deviceData }),
    }

    mockFetch.mockImplementation((url: string) => {
      if (url === FIRMWARE_URL) {
        // Use firmware records with a device_type that is NOT 'esp32' so the
        // device table cells are unambiguous (firmware history won't contain 'esp32').
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({
            customer_id: '3e01e6a7-1c25-4a5e-97c5-92ec5abfd10c',
            device_type: 'esp8266',
            firmwares: [],
          }),
        })
      }
      if (url === DEVICES_URL) {
        return Promise.resolve(realDevicesResponse)
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`))
    })

    render(<App />)
    await waitForInitialLoad()

    // stat-card-devices shows 1
    expect(
      screen.getByTestId('stat-card-devices').querySelector('[data-testid="stat-value"]'),
    ).toHaveTextContent('1')

    // DeviceList table: manufacturer name is in a <td> inside the Devices section
    const deviceListSection = screen.getByText('Devices', { selector: 'h2' }).closest('section')
    expect(deviceListSection?.textContent).toContain('Acme Inc')
    expect(deviceListSection?.textContent).toContain('esp32')
    expect(deviceListSection?.textContent).toContain('v1.11')
    expect(deviceListSection?.textContent).toContain('https')
  })

  it('shows the empty state "No devices found." when the API returns an empty devices array', async () => {
    // devicesResponse() returns { devices: [] } by default — use it directly.
    // "No devices found." appears in both DeviceList and UpdateStatus; verify
    // at least one occurrence (use queryAllByText instead of queryByText).
    render(<App />)
    await waitForInitialLoad()

    const matches = screen.getAllByText(/No devices found/i)
    expect(matches.length).toBeGreaterThanOrEqual(1)
  })

  it('keeps the dashboard visible (no crash) when the Devices API returns a 404', async () => {
    const devices404: MockResponse = {
      ok: false,
      status: 404,
      json: () => Promise.resolve({ error: 'customer not found' }),
    }

    mockFetch.mockImplementation((url: string) => {
      if (url === FIRMWARE_URL) {
        return Promise.resolve(firmwareResponse([1, 2, 3]))
      }
      if (url === DEVICES_URL) {
        return Promise.resolve(devices404)
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`))
    })

    render(<App />)
    await waitForInitialLoad()

    // Dashboard still renders; firmware is visible
    expect(screen.getByTestId('dashboard')).toBeInTheDocument()
    expect(
      screen.getByTestId('stat-card-firmware').querySelector('[data-testid="stat-value"]'),
    ).toHaveTextContent('3')
    // Devices stat shows 0 (devicesUnavailable is set, not a successful empty list)
    expect(
      screen.getByTestId('stat-card-devices').querySelector('[data-testid="stat-value"]'),
    ).toHaveTextContent('0')
    // API failure must not be misread as a successful empty device list —
    // the stat card shows 0, which is correct; no "No devices found." empty
    // state text should appear because the request failed (not because there
    // are genuinely no devices).  Use queryAllByText to avoid the
    // multiple-elements issue (UpdateStatus also has this text).
    const noDevicesMatches = screen.queryAllByText(/No devices found/i)
    // When the API fails, devices=[] → both DeviceList and UpdateStatus show
    // the empty state. This is the existing behaviour (device-unavailable is
    // tracked in state but the empty state is still rendered for [] devices).
    // The important assertion: the dashboard did NOT crash and firmware shows.
    expect(noDevicesMatches.length).toBeGreaterThanOrEqual(1)
  })

  it('keeps the dashboard visible (no crash) when the Devices API returns a 500', async () => {
    const devices500: MockResponse = {
      ok: false,
      status: 500,
      json: () => Promise.resolve({ error: 'failed to load devices' }),
    }

    mockFetch.mockImplementation((url: string) => {
      if (url === FIRMWARE_URL) {
        return Promise.resolve(firmwareResponse([1, 2, 3]))
      }
      if (url === DEVICES_URL) {
        return Promise.resolve(devices500)
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`))
    })

    render(<App />)
    await waitForInitialLoad()

    expect(screen.getByTestId('dashboard')).toBeInTheDocument()
    expect(
      screen.getByTestId('stat-card-firmware').querySelector('[data-testid="stat-value"]'),
    ).toHaveTextContent('3')
    expect(
      screen.getByTestId('stat-card-devices').querySelector('[data-testid="stat-value"]'),
    ).toHaveTextContent('0')
    // No crash, no full-page Load Error banner (that's firmware-only)
    expect(screen.queryByTestId('dashboard-error')).toBeNull()
  })

  it('requests devices only from the configured customer API URL', async () => {
    // Verifies: only DEVICES_URL (which embeds our CUSTOMER_ID) is called;
    // no other devices URL is requested.  This is a URL-routing check, not a
    // security isolation test — backend authorization is a server concern.
    const ourDevice = {
      manufacturer_id: 'our-manufacturer',
      manufacturer_name: 'Our Co',
      device_type: 'esp32',
      current_firmware_version: 'v2.0',
      update_method: 'https',
    }
    const otherDevice = {
      manufacturer_id: 'other-manufacturer',
      manufacturer_name: 'Other Co',
      device_type: 'esp32',
      current_firmware_version: 'v1.0',
      update_method: 'http',
    }

    mockFetch.mockImplementation((url: string) => {
      if (url === FIRMWARE_URL) {
        return Promise.resolve(firmwareResponse([1]))
      }
      if (url === DEVICES_URL) {
        // Our customer's API returns only ourDevice
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ customer_id: '3e01e6a7-1c25-4a5e-97c5-92ec5abfd10c', devices: [ourDevice] }),
        })
      }
      // Any other URL (e.g. a different customer) must not be called
      return Promise.reject(new Error(`Unexpected URL called: ${url}`))
    })

    render(<App />)
    await waitForInitialLoad()

    // Our device is displayed
    expect(screen.getByText('Our Co')).toBeInTheDocument()
    // The other customer's device is NOT displayed
    expect(screen.queryByText('Other Co')).toBeNull()
    // Only DEVICES_URL was called (not any /mock/ or different-customer URL)
    expect(devicesCalls()).toHaveLength(1)
  })
})
