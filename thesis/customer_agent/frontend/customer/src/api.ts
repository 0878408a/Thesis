export const CUSTOMER_ID = '3e01e6a7-1c25-4a5e-97c5-92ec5abfd10c'

/**
 * Customer Agent 後端的真實 API base。
 * dev 環境下由 Vite proxy 把 /api 轉發到 Customer Agent public server (port 5001)。
 */
export const getFirmwareUrl = (): string =>
  `/api/customer/${CUSTOMER_ID}/firmware`

/**
 * 裝置清單端點，與 getFirmwareUrl 同一模式。
 * dev 環境下由 Vite proxy 把 /api 轉發到 Customer Agent public server (port 5001)。
 */
export const getDevicesUrl = (): string =>
  `/api/customer/${CUSTOMER_ID}/devices`
