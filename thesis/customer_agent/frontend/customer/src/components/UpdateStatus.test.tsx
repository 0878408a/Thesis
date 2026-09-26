import { screen, render, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import UpdateStatus from './UpdateStatus'
import {
  countNonCurrent,
  findLatestByReleaseDate,
} from '../lib/firmware'
import type { CustomerDevice, FirmwareRecord } from '../types'

const devices: CustomerDevice[] = [
  {
    manufacturer_id: 'm1',
    manufacturer_name: 'Acme Inc',
    device_type: 'esp32',
    current_firmware_version: 'v1.11',
    update_method: 'https',
  },
]

const firmwares: FirmwareRecord[] = [
  {
    object_id: '0xabc',
    manufacturer_id: 'm1',
    manufacturer_name: 'Acme Inc',
    device_type: 'esp32',
    firmware_version: 'v1.12',
    firmware_size: 40960,
    release_date: 300,
  },
  {
    object_id: '0xdef',
    manufacturer_id: 'm1',
    manufacturer_name: 'Acme Inc',
    device_type: 'esp32',
    firmware_version: 'v1.11',
    firmware_size: 40500,
    release_date: 200,
  },
]

describe('UpdateStatus', () => {
  it('shows all five values in the same device row', () => {
    render(
      <UpdateStatus
        devices={devices}
        firmwares={firmwares}
        findLatest={findLatestByReleaseDate}
        countAvailable={countNonCurrent}
      />,
    )

    // Row-level: all values belong to the SAME row, not just page-level existence
    const row = screen.getByRole('row', { name: /esp32/i })
    expect(within(row).getByText('v1.11')).toBeInTheDocument()
    expect(within(row).getByText('v1.12')).toBeInTheDocument()
    expect(within(row).getByText('2')).toBeInTheDocument()
    expect(within(row).getByText('1')).toBeInTheDocument()
  })

  it('shows an empty state without a table when there are no devices', () => {
    render(
      <UpdateStatus
        devices={[]}
        firmwares={firmwares}
        findLatest={findLatestByReleaseDate}
        countAvailable={countNonCurrent}
      />,
    )

    expect(screen.getByText(/No devices found/i)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows device type, current version, and "No firmware records" in the same row', () => {
    const deviceNoFw: CustomerDevice = {
      manufacturer_id: 'm1',
      manufacturer_name: 'Acme Inc',
      device_type: 'raspberry',
      current_firmware_version: 'v2.0',
      update_method: 'https',
    }
    render(
      <UpdateStatus
        devices={[deviceNoFw]}
        firmwares={firmwares} // only esp32 firmwares, no raspberry
        findLatest={findLatestByReleaseDate}
        countAvailable={countNonCurrent}
      />,
    )

    // Row-level: all three values in the same row
    const row = screen.getByRole('row', { name: /raspberry/i })
    expect(within(row).getByText('v2.0')).toBeInTheDocument()
    expect(within(row).getByText('No firmware records')).toBeInTheDocument()
  })
})
