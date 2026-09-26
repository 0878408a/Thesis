import type { FirmwareRecord, CustomerDevice } from '../types'

export function findLatestByReleaseDate(
  firmwares: FirmwareRecord[],
  deviceType: string,
): FirmwareRecord | undefined {
  const matching = firmwares.filter(
    (firmware) => firmware.device_type === deviceType,
  )

  if (matching.length === 0) {
    return undefined
  }

  return matching.reduce((latest, firmware) =>
    firmware.release_date > latest.release_date ? firmware : latest,
  )
}

export function isCurrent(
  firmware: FirmwareRecord,
  device: CustomerDevice,
): boolean {
  return firmware.firmware_version === device.current_firmware_version
}

export function countNonCurrent(
  firmwares: FirmwareRecord[],
  device: CustomerDevice,
): number {
  return firmwares.filter(
    (firmware) =>
      firmware.device_type === device.device_type &&
      !isCurrent(firmware, device),
  ).length
}

/**
 * Sort a copy of the given firmwares by release_date DESC (newest first).
 * Returns a NEW array; the input array is not mutated.
 * NEVER uses firmware_version for ordering.
 */
export function sortFirmwareByReleaseDateDesc(
  firmwares: FirmwareRecord[],
): FirmwareRecord[] {
  return [...firmwares].sort((a, b) => b.release_date - a.release_date)
}

/**
 * Determine whether a firmware record is "Latest" or "Available".
 *
 * A record is "Latest" iff its release_date equals the maximum release_date
 * among the given `firmwares`. Every other record is "Available".
 *
 * The only input used is `release_date` (a numeric timestamp).
 * `firmware_version` is never read and no version comparison/parse occurs.
 */
export function computeFirmwareStatus(
  firmwares: FirmwareRecord[],
  target: FirmwareRecord,
): 'Latest' | 'Available' {
  const maxReleaseDate = firmwares.reduce(
    (max, f) => (f.release_date > max ? f.release_date : max),
    Number.MIN_SAFE_INTEGER,
  )
  return target.release_date === maxReleaseDate ? 'Latest' : 'Available'
}
