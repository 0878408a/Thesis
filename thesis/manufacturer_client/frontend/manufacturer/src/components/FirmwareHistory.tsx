import { useEffect, useState } from 'react'

export type FirmwareHistoryStatus = 'Uploaded' | 'Pending' | 'Failed'

export type FirmwareMetadataRecord = {
  id?: string
  manufacturerId?: string
  firmwareVersion: string
  deviceType: string
  firmwareSize: string
  releaseDate: string
  uploadStatus: FirmwareHistoryStatus
  objectId?: string
}

/*
 * Manufacturer Agent History API 的實際回傳格式
 *
 * 注意：
 * Backend 使用 snake_case，
 * Frontend 使用 camelCase，
 * 所以需要在取得資料後進行 mapping。
 */
type HistoryApiRecord = {
  object_id: string
  metadata_id: number
  firmware_version: string
  device_type: string
  firmware_size: number
  release_date: number
  submit_block_result: string
}

type HistoryResponse = {
  count: number
  next: string | null
  previous: string | null
  results: HistoryApiRecord[]
}

const HISTORY_API = '/internal/manufacturer/history/'

// 將 NTP timestamp 轉成台灣時間：年月日 時分秒
function formatReleaseDate(timestamp: number): string {
  // NTP epoch 與 Unix epoch 相差 2,208,988,800 秒
  const date = new Date((timestamp - 2208988800) * 1000)

  if (Number.isNaN(date.getTime())) {
    return 'Invalid Date'
  }

  // 指定台灣時區，取得各個日期與時間欄位
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

  const values = Object.fromEntries(
    parts.map((part) => [part.type, part.value]),
  )

  return `${values.year}-${values.month}-${values.day} ${values.hour}:${values.minute}:${values.second}`
}

function FirmwareHistory() {
  const [records, setRecords] = useState<FirmwareMetadataRecord[]>([])
  const [page, setPage] = useState(1)
  const [refreshKey, setRefreshKey] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

    // 監聽韌體上傳成功事件，通知歷史紀錄重新載入
  useEffect(() => {
    const handleHistoryUpdated = () => {
      setRefreshKey((current) => current + 1)
    }

    window.addEventListener(
      'firmware-history-updated',
      handleHistoryUpdated,
    )

    return () => {
      window.removeEventListener(
        'firmware-history-updated',
        handleHistoryUpdated,
      )
    }
  }, [])

  useEffect(() => {
    const fetchHistory = async () => {
      setLoading(true)
      setError('')

      try {
        const response = await fetch(`${HISTORY_API}?page=${page}`)

        if (!response.ok) {
          throw new Error(`History API failed: ${response.status}`)
        }

        const data = (await response.json()) as HistoryResponse

        /*
         * Backend API -> Frontend data mapping
         *
         * Backend:
         * firmware_version
         * device_type
         * firmware_size
         * release_date
         * object_id
         *
         * Frontend:
         * firmwareVersion
         * deviceType
         * firmwareSize
         * releaseDate
         * objectId
         */
        const mappedRecords: FirmwareMetadataRecord[] =
          data.results.map((item) => ({
            id: String(item.metadata_id),
            firmwareVersion: item.firmware_version,
            deviceType: item.device_type,
            firmwareSize: String(item.firmware_size),
            releaseDate: formatReleaseDate(item.release_date),

            /*
             * History API 的每一筆資料
             * 已經存在 SubmitBlockRecord，
             * 因此目前顯示為 Uploaded。
             */
            uploadStatus: 'Uploaded',

            objectId: item.object_id,
          }))

        setRecords(mappedRecords)

        // Backend page size = 10
        setTotalPages(
          Math.max(1, Math.ceil(data.count / 10)),
        )
      } catch (error) {
        console.error(
          'Failed to fetch firmware history:',
          error,
        )

        setError('Unable to load firmware history.')
      } finally {
        setLoading(false)
      }
    }

    fetchHistory()
  }, [page, refreshKey])

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Firmware History</h2>
      </div>

      {loading && <p>Loading firmware history...</p>}

      {error && <p>{error}</p>}

      {!loading && !error && (
        <>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Firmware Version</th>
                  <th>Device Type</th>
                  <th>Firmware Size</th>
                  <th>Release Date</th>
                  <th>Upload Status</th>
                  <th>Object ID</th>
                </tr>
              </thead>

              <tbody>
                {records.map((record) => (
                  <tr
                    key={`${record.firmwareVersion}-${record.deviceType}-${record.releaseDate}`}
                  >
                    <td>{record.firmwareVersion}</td>

                    <td>{record.deviceType}</td>

                    <td>{record.firmwareSize} bytes</td>

                    <td>{record.releaseDate}</td>

                    <td>
                      <span
                        className={`table-status ${record.uploadStatus.toLowerCase()}`}
                      >
                        {record.uploadStatus}
                      </span>
                    </td>

                    <td>
                      {record.objectId ? (
                        <a
                          href={`https://explorer.iota.org/object/${record.objectId}?network=testnet`}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {record.objectId}
                        </a>
                      ) : (
                        '-'
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="pagination">
            <button
              disabled={page <= 1}
              onClick={() =>
                setPage((current) => current - 1)
              }
            >
              Previous
            </button>

            <span>
              Page {page} / {totalPages}
            </span>

            <button
              disabled={page >= totalPages}
              onClick={() =>
                setPage((current) => current + 1)
              }
            >
              Next
            </button>
          </div>
        </>
      )}
    </section>
  )
}

export default FirmwareHistory

