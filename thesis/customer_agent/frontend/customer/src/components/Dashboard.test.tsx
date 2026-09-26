import { screen, render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { CustomerDevice, FirmwareRecord } from '../types'
import Dashboard from './Dashboard'

const esp32Device: CustomerDevice = {
  manufacturer_id: 'm1',
  manufacturer_name: 'Acme Inc',
  device_type: 'esp32',
  current_firmware_version: 'v1.11',
  update_method: 'https',
}

const sensorDevice: CustomerDevice = {
  manufacturer_id: 'm2',
  manufacturer_name: 'Beta Corp',
  device_type: 'sensor',
  current_firmware_version: 'v2.0',
  update_method: 'mqtt',
}

function firmware(overrides: Partial<FirmwareRecord>): FirmwareRecord {
  return {
    object_id: '0xabc',
    manufacturer_id: 'm1',
    manufacturer_name: 'Acme Inc',
    device_type: 'esp32',
    firmware_version: 'v1.11',
    firmware_size: 100,
    release_date: 200,
    ...overrides,
  }
}

const esp32Firmwares: FirmwareRecord[] = [
  firmware({
    object_id: '0xabc',
    firmware_version: 'v1.12',
    release_date: 300,
  }),
  firmware({
    object_id: '0xdef',
    firmware_version: 'v1.11',
    release_date: 200,
  }),
]

const sensorFirmwares: FirmwareRecord[] = [
  firmware({
    object_id: '0x111',
    manufacturer_id: 'm2',
    manufacturer_name: 'Beta Corp',
    device_type: 'sensor',
    firmware_version: 'v2.1',
    release_date: 500,
  }),
  firmware({
    object_id: '0x222',
    manufacturer_id: 'm2',
    manufacturer_name: 'Beta Corp',
    device_type: 'sensor',
    firmware_version: 'v2.0',
    release_date: 400,
  }),
]

describe('Dashboard', () => {
  it('renders two independent stat cards with their own label + value', () => {
    render(
      <Dashboard
        devices={[esp32Device]}
        firmwares={esp32Firmwares}
      />,
    )

    const devicesCard = screen.getByTestId('stat-card-devices')
    const firmwareCard = screen.getByTestId('stat-card-firmware')

    // Each card carries its own label and value
    expect(devicesCard).toHaveTextContent('Devices')
    expect(devicesCard).toHaveTextContent('1')
    expect(firmwareCard).toHaveTextContent('Known Firmware')
    expect(firmwareCard).toHaveTextContent('2')

    // Cards are independent: Devices card must not show the firmware count
    expect(devicesCard).not.toHaveTextContent('2')
  })

  it('stat cards show zero values when no data', () => {
    render(<Dashboard devices={[]} firmwares={[]} />)

    const devicesCard = screen.getByTestId('stat-card-devices')
    const firmwareCard = screen.getByTestId('stat-card-firmware')
    expect(devicesCard).toHaveTextContent('0')
    expect(firmwareCard).toHaveTextContent('0')
  })

  it('shows per-device current/latest in the Update Status row', () => {
    render(
      <Dashboard
        devices={[esp32Device]}
        firmwares={esp32Firmwares}
      />,
    )

    // Update Status row: Device Type | Current | Latest | Known Versions | Non-Current
    // esp32: current v1.11, latest v1.12, 2 known versions, 1 non-current
    const row = screen.getByRole('row', {
      name: /esp32\s+v1\.11\s+v1\.12\s+2\s+1/i,
    })
    expect(row).toBeInTheDocument()
  })

  it('maps firmware to the correct device type for multiple devices', () => {
    render(
      <Dashboard
        devices={[esp32Device, sensorDevice]}
        firmwares={[...esp32Firmwares, ...sensorFirmwares]}
      />,
    )

    // Each device row shows its OWN current/latest versions, not the other's
    const esp32Row = screen.getByRole('row', {
      name: /esp32\s+v1\.11\s+v1\.12\s+2\s+1/i,
    })
    const sensorRow = screen.getByRole('row', {
      name: /sensor\s+v2\.0\s+v2\.1\s+2\s+1/i,
    })
    expect(esp32Row).toBeInTheDocument()
    expect(sensorRow).toBeInTheDocument()

    // cross-check: esp32 row must not contain sensor data and vice versa
    expect(esp32Row).not.toHaveTextContent('v2.1')
    expect(sensorRow).not.toHaveTextContent('v1.12')
  })

  it('shows an error state that replaces the normal dashboard', () => {
    render(
      <Dashboard
        devices={[]}
        firmwares={[]}
        error="API error: 500"
      />,
    )

    const errorPanel = screen.getByTestId('dashboard-error')
    expect(errorPanel).toBeInTheDocument()
    expect(errorPanel).toHaveTextContent('Load Error')
    expect(errorPanel).toHaveTextContent('API error: 500')

    // normal dashboard regions are absent
    expect(screen.queryByTestId('stat-card-devices')).not.toBeInTheDocument()
    expect(screen.queryByTestId('stat-card-firmware')).not.toBeInTheDocument()
    expect(screen.queryByTestId('firmware-history')).not.toBeInTheDocument()
  })

  it('renders a device-independent Firmware History section (no devices)', () => {
    render(<Dashboard devices={[]} firmwares={esp32Firmwares} />)

    // stat cards stay in sync: 0 devices but 2 known firmwares
    const devicesCard = screen.getByTestId('stat-card-devices')
    const firmwareCard = screen.getByTestId('stat-card-firmware')
    expect(devicesCard).toHaveTextContent('0')
    expect(firmwareCard).toHaveTextContent('2')

    // Firmware History is independent of devices and still lists all records
    expect(screen.getByTestId('firmware-history')).toBeInTheDocument()
    const records = screen.getAllByTestId('firmware-record')
    expect(records).toHaveLength(2)
    // sorted release_date DESC: v1.12 (300) first, v1.11 (200) second
    expect(records[0]).toHaveTextContent('v1.12')
    expect(records[0]).toHaveTextContent('Latest')
    expect(records[1]).toHaveTextContent('v1.11')
    expect(records[1]).toHaveTextContent('Available')
  })

  it('renders all four dashboard regions', () => {
    render(
      <Dashboard
        devices={[esp32Device]}
        firmwares={esp32Firmwares}
      />,
    )

    // Smoke/integration only: confirm the main regions exist;
    // data detail is covered by the other tests.
    expect(screen.getByTestId('stat-card-devices')).toBeInTheDocument()
    expect(screen.getByTestId('stat-card-firmware')).toBeInTheDocument()
    expect(screen.getByText('Update Status')).toBeInTheDocument()
    expect(screen.getByTestId('firmware-history')).toBeInTheDocument()
  })

  it('renders refresh controls with hint + button; click calls callback once', async () => {
    const onRefreshFirmware = vi.fn()
    const user = userEvent.setup()
    render(
      <Dashboard
        devices={[]}
        firmwares={[]}
        onRefreshFirmware={onRefreshFirmware}
      />,
    )

    const toolbar = screen.getByTestId('dashboard-toolbar')
    const refreshButton = screen.getByTestId('refresh-firmware-button')
    const hint = screen.getByTestId('firmware-refresh-hint')
    const firmwareHistory = screen.getByTestId('firmware-history')

    // toolbar is inside the Firmware History card, button operable
    expect(toolbar).toBeInTheDocument()
    expect(refreshButton).toBeInTheDocument()
    expect(hint).toHaveTextContent(
      'Firmware refreshes automatically every 10 seconds.',
    )
    expect(firmwareHistory).toContainElement(toolbar)

    await user.click(refreshButton)
    expect(onRefreshFirmware).toHaveBeenCalledTimes(1)
  })

  it('swaps the refresh hint for an error message when firmware refresh fails', () => {
    const onRefreshFirmware = vi.fn()
    render(
      <Dashboard
        devices={[]}
        firmwares={[]}
        onRefreshFirmware={onRefreshFirmware}
        firmwareRefreshError="Firmware refresh failed"
      />,
    )

    const error = screen.getByTestId('firmware-refresh-error')
    expect(error).toHaveTextContent('Firmware refresh failed')

    // hint is gone, but the refresh button is still present and operable
    expect(screen.queryByTestId('firmware-refresh-hint')).not.toBeInTheDocument()
    const refreshButton = screen.getByTestId('refresh-firmware-button')
    expect(refreshButton).toBeInTheDocument()
    expect(screen.getByTestId('dashboard-toolbar')).toContainElement(refreshButton)
  })
})
