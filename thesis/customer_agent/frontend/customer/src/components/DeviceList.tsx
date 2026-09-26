import type { CustomerDevice } from '../types'

type DeviceListProps = {
  devices: CustomerDevice[]
}

export default function DeviceList({ devices }: DeviceListProps) {
  if (devices.length === 0) {
    return (
      <section className="panel">
        <h2>Devices</h2>
        <p className="empty-state">No devices found.</p>
      </section>
    )
  }

  return (
    <section className="panel">
      <h2>Devices</h2>
      <div className="table-wrapper">
        <table className="data-table">
          <thead>
            <tr>
              <th>Device Type</th>
              <th>Manufacturer</th>
              <th>Current Firmware</th>
              <th>Update Method</th>
            </tr>
          </thead>
          <tbody>
            {devices.map((device, index) => (
              <tr key={`${device.manufacturer_id}-${index}`}>
                <td>{device.device_type}</td>
                <td>{device.manufacturer_name}</td>
                <td>{device.current_firmware_version}</td>
                <td>{device.update_method}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
