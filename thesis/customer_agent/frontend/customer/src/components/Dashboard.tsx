import type { CustomerDevice, FirmwareRecord } from '../types'
import {
  countNonCurrent,
  findLatestByReleaseDate,
} from '../lib/firmware'
import DeviceList from './DeviceList'
import { FirmwareHistory } from './FirmwareHistory'
import UpdateStatus from './UpdateStatus'

type DashboardProps = {
  devices: CustomerDevice[]
  firmwares: FirmwareRecord[]
  error?: string | null
  firmwareRefreshError?: string | null
  onRefreshFirmware?: () => void
}

export default function Dashboard({
  devices,
  firmwares,
  error,
  firmwareRefreshError,
  onRefreshFirmware,
}: DashboardProps) {
  if (error) {
    return (
      <section className="panel dashboard-error" data-testid="dashboard-error">
        <h2>Load Error</h2>
        <p>{error}</p>
      </section>
    )
  }

  const totalDevices = devices.length
  const knownFirmwareCount = firmwares.length

  const refreshControls = (
    <div className="dashboard-refresh-controls" data-testid="dashboard-toolbar">
      {firmwareRefreshError ? (
        <p
          className="dashboard-refresh-error"
          data-testid="firmware-refresh-error"
        >
          {firmwareRefreshError}
        </p>
      ) : (
        <p
          className="dashboard-refresh-hint"
          data-testid="firmware-refresh-hint"
        >
          Firmware refreshes automatically every 10 seconds.
        </p>
      )}
      {onRefreshFirmware && (
        <button
          className="dashboard-refresh-button"
          type="button"
          onClick={onRefreshFirmware}
          data-testid="refresh-firmware-button"
        >
          Refresh
        </button>
      )}
    </div>
  )

  return (
    <div className="dashboard-grid" data-testid="dashboard">
      <div
        className="overview-card panel" data-testid="stat-card-devices"
      >
        <span className="overview-label" data-testid="stat-label">
          Devices
        </span>
        <span className="overview-value" data-testid="stat-value">
          {totalDevices}
        </span>
      </div>

      <div
        className="overview-card panel" data-testid="stat-card-firmware"
      >
        <span className="overview-label" data-testid="stat-label">
          Known Firmware
        </span>
        <span className="overview-value" data-testid="stat-value">
          {knownFirmwareCount}
        </span>
      </div>

      <DeviceList devices={devices} />

      <UpdateStatus
        devices={devices}
        firmwares={firmwares}
        findLatest={findLatestByReleaseDate}
        countAvailable={countNonCurrent}
      />

      <FirmwareHistory firmwares={firmwares} toolbar={refreshControls} />
    </div>
  )
}
