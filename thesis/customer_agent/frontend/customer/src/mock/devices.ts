import type { CustomerDevice, DevicesResponse } from '../types'

export const mockDevicesResponse: DevicesResponse = {
  customer_id: '3e01e6a7-1c25-4a5e-97c5-92ec5abfd10c',
  devices: [
    {
      manufacturer_id: '123e4567-e89b-12d3-a456-426614174000',
      manufacturer_name: 'Acme Inc',
      device_type: 'esp32',
      current_firmware_version: 'v1.11',
      update_method: 'https',
    },
  ],
}

export const mockDevice: CustomerDevice = mockDevicesResponse.devices[0]
