/**
 * App 整合測試（FirmwareHistory）：不 mock Dashboard，讓真實的
 * Dashboard → FirmwareHistory 流程被覆蓋，確認 device-independent 的
 * Firmware History 區塊在 App 層確實出現。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import App from './App'
import { mockFirmwareRecords } from './mock/firmware'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

function okFirmware() {
  return new Response(JSON.stringify({ firmwares: mockFirmwareRecords }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function okDevices() {
  return new Response(JSON.stringify({ devices: [] }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('App → Dashboard → FirmwareHistory', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    mockFetch.mockReset()
  })

  it('T12 renders Firmware History with Latest/Available status on device-less Dashboard', async () => {
    mockFetch.mockResolvedValue(okFirmware())
    render(<App />)

    await waitFor(
      () => {
        expect(screen.getAllByTestId('firmware-history')).toHaveLength(1)
      },
      { timeout: 15000 },
    )
    // 3 筆 record 全列出（device-independent，不因 devices 為空而消失）
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
    // 至少一個 Latest 與一個 Available status
    const statuses = screen
      .getAllByTestId('firmware-history')
      .flatMap((node) =>
        Array.from(node.querySelectorAll('[data-status]')).map(
          (el) => el.getAttribute('data-status'),
        ),
      )
    expect(statuses).toContain('Latest')
    expect(statuses).toContain('Available')
  })

  it('T13 renders Latest status on the max release_date record', async () => {
    // 依 mockFirmwareRecords，release_date 最大者 = 第一筆 (v1.12, 3820540800)
    mockFetch.mockResolvedValueOnce(okFirmware()).mockResolvedValueOnce(okDevices())
    render(<App />)

    await waitFor(() => {
      expect(screen.getAllByRole('listitem').length).toBe(3)
    })
    const rows = screen.getAllByRole('listitem')
    // 排序 release_date DESC，第一行（最大 release_date）是 Latest
    expect(rows[0].querySelector('[data-status]')?.textContent).toBe('Latest')
  })

  it('T14 renders Available status on non-Latest records', async () => {
    mockFetch.mockResolvedValueOnce(okFirmware()).mockResolvedValueOnce(okDevices())
    render(<App />)

    await waitFor(() => {
      expect(screen.getAllByRole('listitem').length).toBe(3)
    })
    const rows = screen.getAllByRole('listitem')
    // 第 2、3 行（非最大 release_date）是 Available
    expect(rows[1].querySelector('[data-status]')?.textContent).toBe(
      'Available',
    )
    expect(rows[2].querySelector('[data-status]')?.textContent).toBe(
      'Available',
    )
  })

  it('T15 renders readable release_date while sorting numerically by release_date', async () => {
    mockFetch.mockResolvedValueOnce(okFirmware()).mockResolvedValueOnce(okDevices())
    render(<App />)

    await waitFor(() => {
      expect(screen.getAllByRole('listitem').length).toBe(3)
    })
    const rows = screen.getAllByRole('listitem')
    // 排序：release_date DESC（3820540800 第一）
    expect(rows[0].textContent).toContain(mockFirmwareRecords[0].firmware_version)
    // 可讀日期格式 YYYY-MM-DD（由 release_date 3820540800 → 2020-03-07）
    // Find the Release Date field's value: the dd that follows the dt with text "Release Date"
    const allLabels = Array.from(rows[0].querySelectorAll('.fw-field-label'))
    const rdLabel = allLabels.find((el) => el.textContent === 'Release Date')
    const rdValue = rdLabel?.nextElementSibling
    expect(rdValue?.textContent).toMatch(/^\d{4}-\d{2}-\d{2}/)
  })
})
