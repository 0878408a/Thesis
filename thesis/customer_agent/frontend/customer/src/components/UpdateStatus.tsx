import type { CustomerDevice, FirmwareRecord } from '../types'

type UpdateStatusProps = {
  devices: CustomerDevice[]
  firmwares: FirmwareRecord[]
  findLatest: (
    firmwares: FirmwareRecord[],
    deviceType: string,
  ) => FirmwareRecord | undefined
  countAvailable: (
    firmwares: FirmwareRecord[],
    device: CustomerDevice,
  ) => number
}

export default function UpdateStatus({
  devices,
  firmwares,
  findLatest,
  countAvailable,
}: UpdateStatusProps) {
  return (
    <section className="panel">
      <h2>Update Status</h2>

      {devices.length === 0 ? (
        <p className="empty-state">No devices found.</p>
      ) : (
        <div className="table-wrapper">
          <table className="data-table update-status-table">
            <thead>
              <tr>
                <th>Device Type</th>
                <th>Current</th>
                <th>Latest</th>
                <th>Known Versions</th>
                <th>Non-Current</th>
              </tr>
            </thead>

            <tbody>
              {devices.map((device, index) => {
                const latest = findLatest(
                  firmwares,
                  device.device_type,
                )

                const knownCount = firmwares.filter(
                  (firmware) =>
                    firmware.device_type === device.device_type,
                ).length

                if (knownCount === 0) {
                  return (
                    <tr key={`${device.device_type}-${index}`}>
                      <td>{device.device_type}</td>
                      <td>{device.current_firmware_version}</td>
                      <td
                        colSpan={3}
                        className="empty-state table-empty-state"
                      >
                        No firmware records
                      </td>
                    </tr>
                  )
                }

                return (
                  <tr key={`${device.device_type}-${index}`}>
                    <td>{device.device_type}</td>
                    <td>{device.current_firmware_version}</td>
                    <td>{latest?.firmware_version ?? '—'}</td>
                    <td>{knownCount}</td>
                    <td>{countAvailable(firmwares, device)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}