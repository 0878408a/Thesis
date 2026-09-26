import type { ReactNode } from 'react'
import type { FirmwareRecord } from '../types'
import { buildIotaObjectUrl } from '../iota'
import {
  computeFirmwareStatus,
  sortFirmwareByReleaseDateDesc,
} from '../lib/firmware'

interface FirmwareHistoryProps {
  firmwares: FirmwareRecord[]
  toolbar?: ReactNode
}

/**
 * Convert a release_date (NTP timestamp, seconds since 1900-01-01) to a
 * human-readable date string.
 *
 * The API returns `release_date` as an NTP timestamp, NOT a Unix timestamp.
 * To render it correctly we first convert NTP → Unix by subtracting the
 * 70-year epoch offset (2 208 988 800 s). This is a DISPLAY-ONLY conversion;
 * sorting and Latest/Available status still operate on the raw NTP value.
 */
const NTP_TO_UNIX_OFFSET = 2208988800

function formatReadableReleaseDate(ntpTimestamp: number): string {
  const unixSeconds = ntpTimestamp - NTP_TO_UNIX_OFFSET
  return new Intl.DateTimeFormat('en-CA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone: 'UTC',
  }).format(new Date(unixSeconds * 1000))
}

/**
 * Human-readable byte size (display only — raw value unchanged in data).
 */
function formatReadableSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function Field({
  label,
  children,
  valueTestId,
  valueClassName,
}: {
  label: string
  children: ReactNode
  valueTestId?: string
  valueClassName?: string
}) {
  const ddClass = valueClassName
    ? `fw-field-value ${valueClassName}`
    : 'fw-field-value'
  return (
    <div className="fw-field">
      <dt className="fw-field-label">{label}</dt>
      <dd className={ddClass} data-testid={valueTestId}>
        {children}
      </dd>
    </div>
  )
}

/**
 * Device-independent Firmware History view.
 *
 * Each firmware is rendered as its own visual card (definition list of
 * labelled fields) so fields are clearly separated and never glue into
 * one run of text. Records are ordered by release_date DESC; each record's
 * Latest/Available status is decided SOLELY by release_date (never by
 * firmware_version).
 */
export function FirmwareHistory({
  firmwares,
  toolbar,
}: FirmwareHistoryProps) {
  const hasToolbar = toolbar != null

  if (firmwares.length === 0) {
    return (
      <section
        data-testid="firmware-history"
        className="fw-history fw-panel"
        aria-label="Firmware History"
      >
        <div
          className={`fw-history-header${hasToolbar ? ' has-toolbar' : ''}`}
        >
          <h2>Firmware History</h2>
          {hasToolbar && <div className="fw-history-toolbar-slot">{toolbar}</div>}
        </div>
        <p data-testid="firmware-history-empty">No firmware history found.</p>
      </section>
    )
  }

  const sorted = sortFirmwareByReleaseDateDesc(firmwares)

  return (
    <section
      data-testid="firmware-history"
      className="fw-history fw-panel"
      aria-label="Firmware History"
    >
      <div
        className={`fw-history-header${hasToolbar ? ' has-toolbar' : ''}`}
      >
        <h2>Firmware History</h2>
        {hasToolbar && (
          <div className="fw-history-toolbar-slot">{toolbar}</div>
        )}
      </div>
      <ul className="fw-list">
        {sorted.map((firmware) => {
          const status = computeFirmwareStatus(sorted, firmware)
          return (
            <li
              key={firmware.object_id}
              className="fw-record"
              data-testid="firmware-record"
            >
              <div className="fw-record-header">
                <span className="fw-record-title">
                  Firmware {firmware.firmware_version}
                </span>
                <span
                  className={`fw-status-badge ${
                    status === 'Latest'
                      ? 'fw-status-latest'
                      : 'fw-status-available'
                  }`}
                  data-status={status}
                >
                  {status}
                </span>
              </div>
              <dl className="fw-fields">
                <Field label="Version">{firmware.firmware_version}</Field>
                <Field label="Status">{status}</Field>
                <Field label="Device Type">{firmware.device_type}</Field>
                <Field label="Manufacturer">
                  {firmware.manufacturer_name}
                </Field>
                <Field label="Size">
                  {formatReadableSize(firmware.firmware_size)}
                </Field>
                <Field label="Release Date">
                  {formatReadableReleaseDate(firmware.release_date)}
                </Field>
                  <Field
                    label="Object ID"
                    valueTestId="firmware-object-id"
                    valueClassName="fw-long-string"
                  >
                  <span className="fw-long-string">{firmware.object_id}</span>
                </Field>
                <Field label="IOTA Explorer">
                  <a
                    className="fw-iota-link"
                    href={buildIotaObjectUrl(firmware.object_id)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    View on IOTA Explorer
                  </a>
                </Field>
              </dl>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
