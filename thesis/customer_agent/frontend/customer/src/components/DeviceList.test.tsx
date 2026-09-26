import { screen, render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import DeviceList from './DeviceList'

describe('DeviceList', () => {
  it('renders the table headers', () => {
    render(
      <DeviceList
        devices={[
          {
            manufacturer_id: 'm1',
            manufacturer_name: 'Acme Inc',
            device_type: 'esp32',
            current_firmware_version: 'v1.11',
            update_method: 'https',
          },
        ]}
      />,
    )

    expect(screen.getByRole('columnheader', { name: 'Device Type' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Manufacturer' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Current Firmware' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Update Method' })).toBeInTheDocument()
  })

  it('renders a single device row with all fields in the same row', () => {
    render(
      <DeviceList
        devices={[
          {
            manufacturer_id: 'm1',
            manufacturer_name: 'Acme Inc',
            device_type: 'esp32',
            current_firmware_version: 'v1.11',
            update_method: 'https',
          },
        ]}
      />,
    )

    // row-level assertion: all four values belong to the SAME row
    const row = screen.getByRole('row', {
      name: /esp32\s+Acme Inc\s+v1\.11\s+https/i,
    })
    expect(row).toBeInTheDocument()
  })

  it('renders multiple device rows without merging data', () => {
    render(
      <DeviceList
        devices={[
          {
            manufacturer_id: 'm1',
            manufacturer_name: 'Acme Inc',
            device_type: 'esp32',
            current_firmware_version: 'v1.11',
            update_method: 'https',
          },
          {
            manufacturer_id: 'm2',
            manufacturer_name: 'Beta Corp',
            device_type: 'sensor',
            current_firmware_version: 'v2.3',
            update_method: 'mqtt',
          },
        ]}
      />,
    )

    // 1 header row + 2 data rows
    const rows = screen.getAllByRole('row')
    expect(rows).toHaveLength(3)

    const esp32Row = screen.getByRole('row', {
      name: /esp32\s+Acme Inc\s+v1\.11\s+https/i,
    })
    const sensorRow = screen.getByRole('row', {
      name: /sensor\s+Beta Corp\s+v2\.3\s+mqtt/i,
    })
    expect(esp32Row).toBeInTheDocument()
    expect(sensorRow).toBeInTheDocument()

    // cross-check: data is not merged between rows
    expect(esp32Row).not.toHaveTextContent('Beta Corp')
    expect(sensorRow).not.toHaveTextContent('Acme Inc')
  })

  it('shows an empty state without rendering a table', () => {
    render(<DeviceList devices={[]} />)

    expect(screen.getByText(/No devices found/i)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})
