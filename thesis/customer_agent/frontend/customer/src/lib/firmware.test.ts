import { describe, expect, it } from 'vitest'
import {
  computeFirmwareStatus,
  countNonCurrent,
  findLatestByReleaseDate,
  isCurrent,
  sortFirmwareByReleaseDateDesc,
} from './firmware'
import type { CustomerDevice, FirmwareRecord } from '../types'

const device: CustomerDevice = {
  manufacturer_id: 'm1',
  manufacturer_name: 'Acme Inc',
  device_type: 'esp32',
  current_firmware_version: 'v1.11',
  update_method: 'https',
}

const firmwares: FirmwareRecord[] = [
  {
    object_id: 'obj-latest',
    manufacturer_id: 'm1',
    manufacturer_name: 'Acme Inc',
    device_type: 'esp32',
    firmware_version: 'v1.12',
    firmware_size: 120,
    release_date: 300,
  },
  {
    object_id: 'obj-current',
    manufacturer_id: 'm1',
    manufacturer_name: 'Acme Inc',
    device_type: 'esp32',
    firmware_version: 'v1.11',
    firmware_size: 100,
    release_date: 200,
  },
  {
    object_id: 'obj-older',
    manufacturer_id: 'm1',
    manufacturer_name: 'Acme Inc',
    device_type: 'esp32',
    firmware_version: 'v1.10',
    firmware_size: 90,
    release_date: 100,
  },
  {
    object_id: 'obj-other-device',
    manufacturer_id: 'm2',
    manufacturer_name: 'Other Inc',
    device_type: 'raspberry',
    firmware_version: 'v9.99',
    firmware_size: 10,
    release_date: 999,
  },
]

describe('findLatestByReleaseDate', () => {
  it('returns the record with the maximum release_date for the device type', () => {
    expect(findLatestByReleaseDate(firmwares, 'esp32')?.object_id).toBe(
      'obj-latest',
    )
  })

  it('ignores other device types', () => {
    expect(findLatestByReleaseDate(firmwares, 'raspberry')?.object_id).toBe(
      'obj-other-device',
    )
  })

  it('returns undefined when there is no matching device type', () => {
    expect(findLatestByReleaseDate(firmwares, 'unknown')).toBeUndefined()
  })
})

describe('isCurrent', () => {
  it('is true when firmware_version matches the device current_firmware_version', () => {
    const current = firmwares.find(
      (firmware) => firmware.firmware_version === 'v1.11',
    )!
    expect(isCurrent(current, device)).toBe(true)
  })

  it('is false when firmware_version does not match', () => {
    const latest = firmwares.find(
      (firmware) => firmware.firmware_version === 'v1.12',
    )!
    expect(isCurrent(latest, device)).toBe(false)
  })
})

describe('countNonCurrent', () => {
  it('counts only the same device_type records whose version is not current', () => {
    expect(countNonCurrent(firmwares, device)).toBe(2)
  })

  it('is zero when all matching records are current', () => {
    const onlyCurrent: FirmwareRecord[] = [firmwares[1]]
    expect(countNonCurrent(onlyCurrent, device)).toBe(0)
  })
})

describe('sortFirmwareByReleaseDateDesc', () => {
  const mk = (v: string, d: number): FirmwareRecord => ({
    object_id: `obj-${v}-${d}`,
    manufacturer_id: 'm1',
    manufacturer_name: 'Acme Inc',
    device_type: 'esp32',
    firmware_version: v,
    firmware_size: 100,
    release_date: d,
  })

  it('sorts by release_date DESC (newest first)', () => {
    const input = [mk('a', 100), mk('b', 300), mk('c', 200)]
    const sorted = sortFirmwareByReleaseDateDesc(input)
    expect(sorted.map((f) => f.firmware_version)).toEqual(['b', 'c', 'a'])
  })

  it('does not mutate the input array', () => {
    const input = [mk('a', 100), mk('b', 300)]
    const copy = [...input]
    sortFirmwareByReleaseDateDesc(input)
    expect(input).toEqual(copy)
  })

  it('ignores firmware_version order; release_date is the only ordering key', () => {
    // version 字串順序 a < b < c，但 release_date 是 b 最大 → b 排第一
    const input = [mk('a', 1000), mk('b', 3000), mk('c', 2000)]
    const sorted = sortFirmwareByReleaseDateDesc(input)
    expect(sorted[0].firmware_version).toBe('b')
    expect(sorted[0].release_date).toBe(3000)
  })

  it('handles anti-intuitive version names (e.g. "999" is NOT newer than "123")', () => {
    // "999" 數值大但 release_date 小；"123" 數值小但 release_date 最大 → "123" 排第一
    const input = [
      mk('999', 1000),
      mk('456', 2000),
      mk('123', 3000),
    ]
    const sorted = sortFirmwareByReleaseDateDesc(input)
    expect(sorted.map((f) => f.firmware_version)).toEqual(['123', '456', '999'])
  })
})

describe('computeFirmwareStatus', () => {
  const mk = (v: string, d: number): FirmwareRecord => ({
    object_id: `obj-${v}-${d}`,
    manufacturer_id: 'm1',
    manufacturer_name: 'Acme Inc',
    device_type: 'esp32',
    firmware_version: v,
    firmware_size: 100,
    release_date: d,
  })

  it('marks the max release_date record as Latest', () => {
    const all = [mk('123', 3000), mk('456', 2000), mk('999', 1000)]
    expect(computeFirmwareStatus(all, all[0])).toBe('Latest')
    expect(computeFirmwareStatus(all, all[1])).toBe('Available')
    expect(computeFirmwareStatus(all, all[2])).toBe('Available')
  })

  it('decides by release_date, not firmware_version (anti-intuitive)', () => {
    // "999" 數值大但 release_date=1000；"123" 數值小但 release_date=3000
    const nine99 = mk('999', 1000)
    const one23 = mk('123', 3000)
    const all = [nine99, one23]
    expect(computeFirmwareStatus(all, one23)).toBe('Latest')
    expect(computeFirmwareStatus(all, nine99)).toBe('Available')
  })

  it('same version with different release_date → only the larger release_date is Latest', () => {
    const a = mk('v1.0', 1000)
    const b = mk('v1.0', 2000)
    const all = [a, b]
    expect(computeFirmwareStatus(all, b)).toBe('Latest')
    expect(computeFirmwareStatus(all, a)).toBe('Available')
  })

  it('single record is Latest', () => {
    const only = mk('only', 500)
    expect(computeFirmwareStatus([only], only)).toBe('Latest')
  })
})
