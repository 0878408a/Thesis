/**
 * App 整合測試：mock global fetch + mock Dashboard 子元件。
 *
 * 分離載入語意（fix-customer-firmware-load-error）：
 * - Firmware 與 Devices 獨立 fetch，devices 失敗不阻止 firmware 顯示。
 * - Firmware 真正失敗（500 / network / invalid JSON）仍進 Load Error state。
 * - mock 依 `fetch()` 呼叫順序提供回應；App 先取 firmware，再取 devices。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import App from './App'
import { mockFirmwareResponse } from './mock/firmware'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

vi.mock('./components/Dashboard', () => ({
  default: function MockDashboard({
    devices,
    firmwares,
    error,
  }: {
    devices?: unknown[]
    firmwares?: unknown[]
    error?: string | null
  }) {
    if (error) {
      return <div data-testid="dashboard-error">Load Error: {error}</div>
    }
    return (
      <div data-testid="dashboard">
        <div data-testid="firmware-count">{firmwares?.length ?? 0}</div>
        <div data-testid="devices-count">{devices?.length ?? 0}</div>
      </div>
    )
  },
}))

function firmwareResponse(overrides: Partial<ResponseInit> = {}) {
  return new Response(JSON.stringify(mockFirmwareResponse), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...overrides,
  })
}

describe('App', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    mockFetch.mockReset()
  })

  it('displays Customer Portal eyebrow text', () => {
    mockFetch.mockImplementation(() =>
      Promise.resolve(
        new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }),
      ),
    )
    render(<App />)
    expect(screen.getByText('Customer Portal')).toBeInTheDocument()
  })

  it('shows Dashboard when both firmware and devices load successfully', async () => {
    // App 先取 firmware、再取 devices；依序提供兩個 200 JSON 回應。
    mockFetch
      .mockResolvedValueOnce(firmwareResponse())
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ customer_id: 'x', devices: [{ device_type: 'esp32' }] }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      )

    render(<App />)
    await waitFor(() => {
      expect(screen.getByTestId('dashboard')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('dashboard-error')).toBeNull()
  })

  it('shows Dashboard (firmware visible) when devices endpoint is not yet implemented (404)', async () => {
    // firmware 正常；devices 端點尚未實作 → 404。Firmware 不應被阻止。
    mockFetch
      .mockResolvedValueOnce(firmwareResponse())
      .mockResolvedValueOnce(
        new Response('', { status: 404, headers: { 'Content-Type': 'application/json' } }),
      )

    render(<App />)
    await waitFor(() => {
      expect(screen.getByTestId('dashboard')).toBeInTheDocument()
    })
    // firmware records 有傳入 Dashboard（3 筆），且無 Load Error
    expect(screen.getByTestId('firmware-count').textContent).toBe('3')
    expect(screen.queryByTestId('dashboard-error')).toBeNull()
  })

  it('shows Load Error when firmware API returns 500 (no mock fallback)', async () => {
    mockFetch
      .mockResolvedValueOnce(
        new Response('', { status: 500, headers: { 'Content-Type': 'application/json' } }),
      )
      .mockResolvedValueOnce(firmwareResponse())

    render(<App />)
    await waitFor(() => {
      expect(screen.getByTestId('dashboard-error')).toBeInTheDocument()
    })
    expect(screen.getByTestId('dashboard-error').textContent).toContain('500')
  })

  it('shows Load Error when firmware fetch rejects (network error)', async () => {
    mockFetch
      .mockRejectedValueOnce(new Error('Network error: failed to fetch'))
      .mockResolvedValueOnce(firmwareResponse())

    render(<App />)
    await waitFor(() => {
      expect(screen.getByTestId('dashboard-error')).toBeInTheDocument()
    })
    expect(screen.getByTestId('dashboard-error').textContent).toContain('Network error')
  })

  it('shows Load Error when firmware response body is invalid JSON', async () => {
    // response.ok === true 但 json() reject → 不能偽裝成功
    const badResponse = new Response('<!doctype html><html></html>', {
      status: 200,
      headers: { 'Content-Type': 'text/html' },
    })
    mockFetch
      .mockResolvedValueOnce(badResponse)
      .mockResolvedValueOnce(firmwareResponse())

    render(<App />)
    await waitFor(() => {
      expect(screen.getByTestId('dashboard-error')).toBeInTheDocument()
    })
  })
})
