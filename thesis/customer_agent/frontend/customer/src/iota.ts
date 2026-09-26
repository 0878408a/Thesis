/**
 * IOTA Testnet Explorer base URL.
 * Aligned with manufacturer frontend pattern (FirmwareHistory.tsx / UploadStatus.tsx).
 * NOTE: URL confirmation still pending (Open Question in design.md).
 * Do NOT change without verifying with backend / product.
 */
export const IOTA_TESTNET_EXPLORER_BASE = 'https://explorer.iota.org'

/**
 * Query string parameter that pins the link to the Testnet (not Mainnet).
 */
export const IOTA_TESTNET_NETWORK_PARAM = 'network=testnet'

export function buildIotaObjectUrl(objectId: string): string {
  return `${IOTA_TESTNET_EXPLORER_BASE}/object/${objectId}?${IOTA_TESTNET_NETWORK_PARAM}`
}
