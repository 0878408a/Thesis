import { describe, expect, it } from 'vitest'
import {
  IOTA_TESTNET_EXPLORER_BASE,
  IOTA_TESTNET_NETWORK_PARAM,
  buildIotaObjectUrl,
} from './iota'

describe('buildIotaObjectUrl', () => {
  it('builds {base}/object/{object_id}?network=testnet using centralized constants', () => {
    const url = buildIotaObjectUrl('0xabc')
    expect(url).toBe(
      `${IOTA_TESTNET_EXPLORER_BASE}/object/0xabc?${IOTA_TESTNET_NETWORK_PARAM}`,
    )
  })

  it('base URL is HTTPS', () => {
    expect(IOTA_TESTNET_EXPLORER_BASE).toMatch(/^https:\/\//)
  })

  it('URL points to Testnet, not Mainnet', () => {
    const url = buildIotaObjectUrl('0xabc')
    expect(url).toContain('network=testnet')
    // Must NOT point to Mainnet
    expect(url).not.toContain('network=mainnet')
    expect(url).not.toContain('mainnet')
  })

  it('object path is correctly composed with object_id', () => {
    const objectId =
      '0x1111222233334444555566667777888899990000aabbccddeeff001122334455'
    const url = buildIotaObjectUrl(objectId)
    expect(url).toContain(`/object/${objectId}`)
  })
})
