import type { FirmwareRecord } from '../types'
import { buildIotaObjectUrl } from '../iota'

/*
 * 將 NTP timestamp 轉成台灣時間：年月日 時分秒
 */
function formatReleaseDate(timestamp: number): string {
  // NTP epoch 與 Unix epoch 相差 2,208,988,800 秒
  const date = new Date((timestamp - 2208988800) * 1000)

  if (Number.isNaN(date.getTime())) {
    return 'Invalid Date'
  }

  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Taipei',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date)

  const values = Object.fromEntries(parts.map((p) => [p.type, p.value]))

  return `${values.year}-${values.month}-${values.day} ${values.hour}:${values.minute}:${values.second}`
}

type FirmwareListProps = {
  deviceType: string
  firmwares: FirmwareRecord[]
  currentVersion?: string
  latestVersion?: string
}

export default function FirmwareList({
  deviceType,
  firmwares,
  currentVersion,
  latestVersion,
}: FirmwareListProps) {
  if (firmwares.length === 0) {
    return (
      <section className="panel">
        <h2>Firmware</h2>
        <p className="empty-state">No firmware records found.</p>
      </section>
    )
  }

  const sorted = [...firmwares].sort(
    (a, b) => b.release_date - a.release_date,
  )

  function markerFor(firmware: FirmwareRecord): string {
    if (
      firmware.firmware_version === currentVersion &&
      firmware.firmware_version === latestVersion
    ) {
      return 'Current + Latest'
    }
    if (firmware.firmware_version === currentVersion) {
      return 'Current'
    }
    if (firmware.firmware_version === latestVersion) {
      return 'Latest'
    }
    return 'Available'
  }

  return (
    <section className="panel">
      <h2>Firmware ({deviceType})</h2>
      <div className="table-wrapper">
        <table className="data-table">
          <thead>
            <tr>
              <th>Version</th>
              <th>Size (bytes)</th>
              <th>Release Date</th>
              <th>Status</th>
              <th>Object</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((firmware) => (
              <tr key={firmware.object_id}>
                <td>{firmware.firmware_version}</td>
                <td>{firmware.firmware_size.toLocaleString()}</td>
                <td>{formatReleaseDate(firmware.release_date)}</td>
                <td>
                  <span
                    className={`table-status ${
                      markerFor(firmware).toLowerCase().replace(' ', '-')
                    }`}
                  >
                    {markerFor(firmware)}
                  </span>
                </td>
                <td>
                  <a
                    className="iota-link"
                    href={buildIotaObjectUrl(firmware.object_id)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {firmware.object_id}
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
