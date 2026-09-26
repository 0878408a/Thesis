import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { FirmwareHistory } from './FirmwareHistory'
import type { FirmwareRecord } from '../types'

const base = {
  manufacturer_id: 'm1',
  manufacturer_name: 'Acme Inc',
  device_type: 'esp32',
  firmware_size: 120,
}

// 反直覺：version "999" 數值大但 release_date 小；"123" 數值小但 release_date 大
const nine99: FirmwareRecord = {
  ...base,
  object_id: 'obj-999',
  firmware_version: '999',
  release_date: 1000,
}
const four56: FirmwareRecord = {
  ...base,
  object_id: 'obj-456',
  firmware_version: '456',
  release_date: 2000,
}
const one23: FirmwareRecord = {
  ...base,
  object_id: 'obj-123',
  firmware_version: '123',
  release_date: 3000,
}

// 完整長 object_id（66 字元 hex）— 用來驗證「不截斷 + 換行 class」
const longObjectId =
  '0x14124049c5f96cb42ea512f0bae19bd725cfdca3cf5c4ae6eec5075c56883c80'
const longFw: FirmwareRecord = {
  ...base,
  object_id: longObjectId,
  firmware_version: '456',
  firmware_size: 1247776,
  release_date: 3000,
}

describe('FirmwareHistory — responsive UI layout', () => {
  // ---- T1: 每筆 firmware 是獨立區塊 ----
  it('T1: renders one independent record block per firmware', () => {
    render(<FirmwareHistory firmwares={[one23, four56]} />)
    const records = screen.getAllByTestId('firmware-record')
    expect(records).toHaveLength(2)
    // 每筆的欄位都在自己區塊內
    const [first, second] = records
    expect(first.textContent).toContain('123')
    expect(first.textContent).toContain('obj-123')
    expect(second.textContent).toContain('456')
    expect(second.textContent).toContain('obj-456')
    // 不同筆的 object_id 不會混在同一區塊
    expect(first.textContent).not.toContain('obj-456')
    expect(second.textContent).not.toContain('obj-123')
  })

  // ---- T2: 欄位以 label 清楚呈現 ----
  it('T2: each field has a recognizable label in the DOM', () => {
    render(<FirmwareHistory firmwares={[one23]} />)
    const record = screen.getByTestId('firmware-record')
    // 各欄位 label 存在
    expect(record.textContent).toContain('Version')
    expect(record.textContent).toContain('Status')
    expect(record.textContent).toContain('Device Type')
    expect(record.textContent).toContain('Manufacturer')
    expect(record.textContent).toContain('Size')
    expect(record.textContent).toContain('Release Date')
    expect(record.textContent).toContain('Object ID')
    expect(record.textContent).toContain('IOTA Explorer')
  })

  it('T2: firmware_version shows its original value (no parsing)', () => {
    const v002: FirmwareRecord = { ...base, object_id: 'obj-v002', firmware_version: 'v0.0.2', release_date: 200 }
    const raw: FirmwareRecord = { ...base, object_id: 'obj-456', firmware_version: '456', release_date: 100 }
    render(<FirmwareHistory firmwares={[v002, raw]} />)
    const records = screen.getAllByTestId('firmware-record')
    expect(records[0].textContent).toContain('v0.0.2')
    expect(records[1].textContent).toContain('456')
  })

  // ---- T3: 長 Object ID 完整顯示 + 換行 class ----
  it('T3: full long object_id is shown (not truncated) with a long-string wrap class', () => {
    render(<FirmwareHistory firmwares={[longFw]} />)
    const record = screen.getByTestId('firmware-record')
    // 完整 object_id 存在於 DOM（不截斷）
    const objectIdValue = record.querySelector<HTMLElement>('[data-testid="firmware-object-id"]')
    expect(objectIdValue).not.toBeNull()
    expect(objectIdValue!.textContent).toBe(longObjectId)
    // 長字串換行 class 存在（CSS 端使用 overflow-wrap / word-break）
    expect(objectIdValue!.className).toContain('fw-long-string')
    // IOTA href 正確
    const link = screen.getByRole('link', { name: /View on IOTA Explorer/i })
    expect(link).toHaveAttribute(
      'href',
      `https://explorer.iota.org/object/${longObjectId}?network=testnet`,
    )
  })

  // ---- T4: Explorer link 短文案 + contract ----
  it('T4: IOTA link uses short text with correct href / target / rel', () => {
    render(<FirmwareHistory firmwares={[one23, four56]} />)
    const links = screen.getAllByRole('link', { name: /View on IOTA Explorer/i })
    expect(links).toHaveLength(2)
    const first = links[0]
    expect(first.textContent).toBe('View on IOTA Explorer')
    expect(first).toHaveAttribute(
      'href',
      'https://explorer.iota.org/object/obj-123?network=testnet',
    )
    expect(first).toHaveAttribute('target', '_blank')
    expect(first).toHaveAttribute('rel', 'noopener noreferrer')
    // 長 object_id 不以 URL 當顯示文字
    const longRender = render(
      <FirmwareHistory firmwares={[longFw]} />,
    )
    const longQuery = within(longRender.container)
    const longLink = longQuery.getAllByRole('link', { name: /View on IOTA Explorer/i })[0]
    expect(longLink.textContent).toBe('View on IOTA Explorer')
    // 完整 object_id 仍顯示於 Object ID 欄（非 link 文字）
    expect(
      longQuery.getByTestId('firmware-object-id').textContent,
    ).toBe(longObjectId)
    longRender.unmount()
  })

  // ---- T5: Latest / Available UI（reuse 既有判定邏輯） ----
  it('T5: max release_date record shows Latest, others show Available', () => {
    render(<FirmwareHistory firmwares={[nine99, four56, one23]} />)
    const records = screen.getAllByTestId('firmware-record')
    // 排序後 123(rd3000) 第一 → Latest
    // "Latest" appears twice per record (badge + Status field), use getAllByText
    expect(within(records[0]).getAllByText('Latest').length).toBe(2)
    expect(within(records[0]).getByText('123')).toBeInTheDocument()
    // 其餘 → Available
    expect(within(records[1]).getAllByText('Available').length).toBe(2)
    expect(within(records[2]).getAllByText('Available').length).toBe(2)
    // Cross-check: the Latest record does NOT also show "Available"
    expect(within(records[0]).queryAllByText('Available')).toHaveLength(0)
  })

  it('T5: ignores firmware_version (999 higher numeric is still Available, 123 lower is Latest)', () => {
    render(<FirmwareHistory firmwares={[nine99, one23]} />)
    const records = screen.getAllByTestId('firmware-record')
    expect(records[0].textContent).toContain('123')
    expect(records[0].textContent).toContain('Latest')
    expect(records[1].textContent).toContain('999')
    expect(records[1].textContent).toContain('Available')
  })

  // ---- T6: Empty state ----
  it('T6: empty firmwares shows message and no record cards', () => {
    render(<FirmwareHistory firmwares={[]} />)
    expect(screen.getByTestId('firmware-history-empty')).toHaveTextContent(
      'No firmware history found',
    )
    expect(screen.queryAllByTestId('firmware-record')).toHaveLength(0)
  })

  // ---- T7: responsive / structure classes ----
  it('T7: record container and object_id long-string class exist (structure for responsive CSS)', () => {
    render(<FirmwareHistory firmwares={[longFw]} />)
    const record = screen.getByTestId('firmware-record')
    // record 區塊有 responsive container class
    expect(record.className).toContain('fw-record')
    // 長字串換行 class
    expect(
      record.querySelector('[data-testid="firmware-object-id"]')!.className,
    ).toContain('fw-long-string')
    // 整個 Firmware History 區塊 container 有 responsive class
    expect(screen.getByTestId('firmware-history').className).toContain(
      'fw-history',
    )
  })

  // ---- T8: NTP timestamp 顯示為 2026（非 2096）----
  it('T8: NTP release_date 3998805834 displays as 2026-09-19 (not 2096)', () => {
    const ntpFw: FirmwareRecord = { ...base, object_id: 'obj-ntp-a', firmware_version: 'v3.0', release_date: 3998805834 }
    render(<FirmwareHistory firmwares={[ntpFw]} />)
    const record = screen.getByTestId('firmware-record')
    const allLabels = Array.from(record.querySelectorAll('.fw-field-label'))
    const rdLabel = allLabels.find((el) => el.textContent === 'Release Date')
    const rdValue = rdLabel?.nextElementSibling
    expect(rdValue?.textContent).toContain('2026-09-19')
    expect(rdValue?.textContent).not.toContain('2096')
  })

  it('T8: NTP release_date 3998805037 displays as 2026-09-19 (not 2096)', () => {
    const ntpFw: FirmwareRecord = { ...base, object_id: 'obj-ntp-b', firmware_version: 'v3.1', release_date: 3998805037 }
    render(<FirmwareHistory firmwares={[ntpFw]} />)
    const record = screen.getByTestId('firmware-record')
    const allLabels = Array.from(record.querySelectorAll('.fw-field-label'))
    const rdLabel = allLabels.find((el) => el.textContent === 'Release Date')
    const rdValue = rdLabel?.nextElementSibling
    expect(rdValue?.textContent).toContain('2026-09-19')
    expect(rdValue?.textContent).not.toContain('2096')
  })
})
