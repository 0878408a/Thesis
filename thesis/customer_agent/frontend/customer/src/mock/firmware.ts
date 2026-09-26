import type { FirmwareRecord, FirmwareResponse } from '../types'

export const mockFirmwareRecords: FirmwareRecord[] = [
  {
    object_id: '0xabc123',
    manufacturer_id: '123e4567-e89b-12d3-a456-426614174000',
    manufacturer_name: 'Acme Inc',
    device_type: 'esp32',
    firmware_version: 'v1.12',
    firmware_size: 40960,
    release_date: 3820540800,
  },
  {
    object_id: '0xdef456',
    manufacturer_id: '123e4567-e89b-12d3-a456-426614174000',
    manufacturer_name: 'Acme Inc',
    device_type: 'esp32',
    firmware_version: 'v1.11',
    firmware_size: 40500,
    release_date: 3820454400,
  },
  {
    object_id: '0x789abc',
    manufacturer_id: '123e4567-e89b-12d3-a456-426614174000',
    manufacturer_name: 'Acme Inc',
    device_type: 'esp32',
    firmware_version: 'v1.10',
    firmware_size: 40000,
    release_date: 3820368000,
  },
]

export const mockFirmwareResponse: FirmwareResponse = {
  customer_id: '3e01e6a7-1c25-4a5e-97c5-92ec5abfd10c',
  device_type: 'esp32',
  firmwares: mockFirmwareRecords,
}
