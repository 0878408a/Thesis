export type CustomerDevice = {
  manufacturer_id: string
  manufacturer_name: string
  device_type: string
  current_firmware_version: string
  update_method: string
}

export type FirmwareRecord = {
  object_id: string
  manufacturer_id: string
  manufacturer_name: string
  device_type: string
  firmware_version: string
  firmware_size: number
  release_date: number
}

export type DevicesResponse = {
  customer_id: string
  devices: CustomerDevice[]
}

export type FirmwareResponse = {
  customer_id: string
  device_type: string
  firmwares: FirmwareRecord[]
}
