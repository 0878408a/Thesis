import { screen, render, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import FirmwareList from './FirmwareList'
import type { FirmwareRecord } from '../types'

function makeFirmware(overrides: Partial<FirmwareRecord> & Pick<FirmwareRecord, 'object_id' | 'firmware_version' | 'release_date'>): FirmwareRecord {
  return {
    manufacturer_id: 'm1',
    manufacturer_name: 'Acme Inc',
    device_type: 'esp32',
    firmware_size: 100,
    ...overrides,
  }
}

describe('FirmwareList', () => {
  it('shows three firmware rows in release_date DESC order, each with its own status and release date', () => {
    const firmwares = [
      makeFirmware({ object_id: 'obj-v110', firmware_version: 'v1.10', release_date: 100, firmware_size: 100 }),
      makeFirmware({ object_id: 'obj-v111', firmware_version: 'v1.11', release_date: 200, firmware_size: 200 }),
      makeFirmware({ object_id: 'obj-v112', firmware_version: 'v1.12', release_date: 300, firmware_size: 300 }),
    ]
    render(
      <FirmwareList
        deviceType="esp32"
        firmwares={firmwares}
        currentVersion="v1.11"
        latestVersion="v1.12"
      />,
    )

    // 1 header row + 3 data rows
    const rows = screen.getAllByRole('row')
    expect(rows).toHaveLength(4)

    // Release date DESC: v1.12 (300), v1.11 (200), v1.10 (100)
    const row1 = screen.getByText('v1.12').closest('tr')!
    const row2 = screen.getByText('v1.11').closest('tr')!
    const row3 = screen.getByText('v1.10').closest('tr')!
    // Row order in DOM confirms DESC sort
    expect(rows[1]!.contains(row1)).toBe(true)
    expect(rows[2]!.contains(row2)).toBe(true)
    expect(rows[3]!.contains(row3)).toBe(true)

    // Each version's status belongs to its own row
    expect(within(row1).getByText('Latest')).toBeInTheDocument()
    expect(within(row2).getByText('Current')).toBeInTheDocument()
    expect(within(row3).getByText('Available')).toBeInTheDocument()

    // Each version's release date (formatted NTP → Asia/Taipei) belongs to its own row
    // release_date 300 → "01/01/1900, 08:05:00", 200 → "01/01/1900, 08:03:20", 100 → "01/01/1900, 08:01:40"
    expect(within(row1).getByText(/08:05:00/)).toBeInTheDocument()
    expect(within(row2).getByText(/08:03:20/)).toBeInTheDocument()
    expect(within(row3).getByText(/08:01:40/)).toBeInTheDocument()

    // Cross-check: v1.12's row does NOT contain v1.11's status
    expect(within(row1).queryByText('Current')).toBeNull()
  })

  it('marks Current correctly (v1.11 = currentVersion)', () => {
    const firmwares = [
      makeFirmware({ object_id: 'a', firmware_version: 'v1.10', release_date: 100 }),
      makeFirmware({ object_id: 'b', firmware_version: 'v1.11', release_date: 200 }),
      makeFirmware({ object_id: 'c', firmware_version: 'v1.12', release_date: 300 }),
    ]
    render(
      <FirmwareList
        deviceType="esp32"
        firmwares={firmwares}
        currentVersion="v1.11"
        latestVersion="v1.12"
      />,
    )

    const currentBadge = screen.getByText('Current', { exact: true })
    expect(currentBadge).toBeInTheDocument()
    // The row for v1.11 should have the "Current" badge
    const v111Row = screen.getByText('v1.11').closest('tr')
    expect(v111Row?.textContent).toContain('Current')
  })

  it('marks Latest correctly (v1.12 = latestVersion, release_date max)', () => {
    const firmwares = [
      makeFirmware({ object_id: 'a', firmware_version: 'v1.10', release_date: 100 }),
      makeFirmware({ object_id: 'b', firmware_version: 'v1.11', release_date: 200 }),
      makeFirmware({ object_id: 'c', firmware_version: 'v1.12', release_date: 300 }),
    ]
    render(
      <FirmwareList
        deviceType="esp32"
        firmwares={firmwares}
        currentVersion="v1.10"
        latestVersion="v1.12"
      />,
    )

    const v112Row = screen.getByText('v1.12').closest('tr')
    expect(v112Row?.textContent).toContain('Latest')
  })

  it('marks non-current non-latest firmware as Available', () => {
    const firmwares = [
      makeFirmware({ object_id: 'a', firmware_version: 'v1.10', release_date: 100 }),
      makeFirmware({ object_id: 'b', firmware_version: 'v1.11', release_date: 200 }),
      makeFirmware({ object_id: 'c', firmware_version: 'v1.12', release_date: 300 }),
    ]
    render(
      <FirmwareList
        deviceType="esp32"
        firmwares={firmwares}
        currentVersion="v1.10"
        latestVersion="v1.12"
      />,
    )

    // v1.11 is neither current (v1.10) nor latest (v1.12), so it should be "Available"
    const v111Row = screen.getByText('v1.11').closest('tr')
    expect(v111Row?.textContent).toContain('Available')
  })

  it('Current + Latest badge when currentVersion equals latestVersion', () => {
    const firmwares = [
      makeFirmware({ object_id: 'a', firmware_version: 'v1.10', release_date: 100 }),
      makeFirmware({ object_id: 'b', firmware_version: 'v1.11', release_date: 200 }),
      makeFirmware({ object_id: 'c', firmware_version: 'v1.12', release_date: 300 }),
    ]
    render(
      <FirmwareList
        deviceType="esp32"
        firmwares={firmwares}
        currentVersion="v1.12"
        latestVersion="v1.12"
      />,
    )

    const v112Row = screen.getByText('v1.12').closest('tr')
    expect(v112Row?.textContent).toContain('Current + Latest')
  })

  it('Latest is determined by release_date, not firmware_version name', () => {
    // Even though "v1.10" looks "older" by name, it has the largest release_date
    const firmwares = [
      makeFirmware({ object_id: 'a', firmware_version: 'v1.12', release_date: 100 }),
      makeFirmware({ object_id: 'b', firmware_version: 'v1.10', release_date: 999 }),
    ]
    render(
      <FirmwareList
        deviceType="esp32"
        firmwares={firmwares}
        currentVersion="v1.12"
        latestVersion="v1.10" // latestVersion is passed by parent based on release_date
      />,
    )

    // v1.10 has the largest release_date, so it should show "Latest"
    const v110Row = screen.getByText('v1.10').closest('tr')
    expect(v110Row?.textContent).toContain('Latest')
  })

  it('irregular firmware version names still display correctly and Latest follows release_date', () => {
    const firmwares = [
      makeFirmware({ object_id: 'obj-alpha', firmware_version: 'alpha-rc1', release_date: 50 }),
      makeFirmware({ object_id: 'obj-date', firmware_version: '20241015-build.3', release_date: 200 }),
      makeFirmware({ object_id: 'obj-final', firmware_version: 'release-final', release_date: 100 }),
    ]
    render(
      <FirmwareList
        deviceType="esp32"
        firmwares={firmwares}
        currentVersion="alpha-rc1"
        latestVersion="20241015-build.3" // largest release_date
      />,
    )

    expect(screen.getByText('alpha-rc1')).toBeInTheDocument()
    expect(screen.getByText('20241015-build.3')).toBeInTheDocument()
    expect(screen.getByText('release-final')).toBeInTheDocument()

    // "20241015-build.3" has the max release_date (200) → Latest
    const dateRow = screen.getByText('20241015-build.3').closest('tr')
    expect(dateRow?.textContent).toContain('Latest')

    // "alpha-rc1" is current → Current
    const alphaRow = screen.getByText('alpha-rc1').closest('tr')
    expect(alphaRow?.textContent).toContain('Current')

    // "release-final" is neither current nor latest → Available
    const finalRow = screen.getByText('release-final').closest('tr')
    expect(finalRow?.textContent).toContain('Available')
  })

  it('NTP timestamp is formatted as Asia/Taipei date string', () => {
    // NTP timestamp 3914265600 = 2024-01-15 00:00:00 UTC = 2024-01-15 08:00:00 Asia/Taipei
    const firmwares = [
      makeFirmware({ object_id: 'obj-ntp', firmware_version: 'v1.0', release_date: 3914265600 }),
    ]
    render(
      <FirmwareList
        deviceType="esp32"
        firmwares={firmwares}
      />,
    )

    const row = screen.getByText('v1.0').closest('tr')
    expect(row?.textContent).toContain('2024-01-15')
    expect(row?.textContent).toContain('08:00:00')
  })

  // ---- NTP timestamp conversion (real-world values) ----
  it('NTP 3998805834 displays as 2026-09-19 (not 2096)', () => {
    const firmwares = [
      makeFirmware({ object_id: 'obj-a', firmware_version: 'v2.0', release_date: 3998805834 }),
    ]
    render(<FirmwareList deviceType="esp32" firmwares={firmwares} />)
    const row = screen.getByText('v2.0').closest('tr')
    expect(row?.textContent).toContain('2026-09-19')
    expect(row?.textContent).not.toContain('2096')
  })

  it('NTP 3998805037 displays as 2026-09-19', () => {
    const firmwares = [
      makeFirmware({ object_id: 'obj-b', firmware_version: 'v2.1', release_date: 3998805037 }),
    ]
    render(<FirmwareList deviceType="esp32" firmwares={firmwares} />)
    const row = screen.getByText('v2.1').closest('tr')
    expect(row?.textContent).toContain('2026-09-19')
    expect(row?.textContent).not.toContain('2096')
  })

  it('object_id is rendered as <a> link with correct href, target, and rel', () => {
    const firmwares = [
      makeFirmware({ object_id: '0xabc123', firmware_version: 'v1.0', release_date: 100 }),
    ]
    render(
      <FirmwareList
        deviceType="esp32"
        firmwares={firmwares}
      />,
    )

    const link = screen.getByRole('link', { name: '0xabc123' })
    // href must use the centralized builder URL (contains object_id + network=testnet)
    expect(link).toHaveAttribute('href', expect.stringContaining('0xabc123'))
    expect(link).toHaveAttribute('href', expect.stringContaining('network=testnet'))
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('shows an empty state when there are no firmware records', () => {
    render(
      <FirmwareList
        deviceType="esp32"
        firmwares={[]}
        currentVersion="v1.11"
        latestVersion="v1.12"
      />,
    )

    expect(screen.getByText(/No firmware records found/i)).toBeInTheDocument()
  })
})
