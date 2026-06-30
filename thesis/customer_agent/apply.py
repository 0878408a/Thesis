import requests
import serial
import time
import config
from db import get_devices_by_customer_and_version, get_firmware_by_version, mark_device_updated

# 憑證與私鑰路徑
CUSTOMER_CERT_PATH = config.CUSTOMER_CERT_PATH
CUSTOMER_KEY_PATH = config.CUSTOMER_KEY_PATH
CA_CERT_PATH = config.CA_CERT_PATH
MANUFACTURER_CERT_PATH = config.MANUFACTURER_AGENT_CERT_PATH

# 根據更新方式呼叫對應子函式
def update_device(method, address, firmware_version):
    if method == "https":
        return update_https(address, firmware_version)
    elif method == "serial":
        return update_serial(address, firmware_version)
    else:
        print(f"不支援的更新方式: {method}")
        return False

# HTTP 傳送更新訊息（使用 mTLS）
def update_https(ip, firmware_version):
    try:
        url = f"http://{ip}:80/trigger_update"

        resp = requests.post(
            url,
            json={"version": firmware_version},
            timeout=10
        )

        print(resp.status_code, resp.text)
        if resp.status_code == 200:
            print(f"{ip} 已成功觸發 OTA 更新")
            return True
        else:
            print(f"{ip} 觸發 OTA 更新失敗: {resp.text}")
            return False

    except Exception as e:
        print("[Trigger OTA 錯誤]", e)
        return False


# Serial 傳送：包含握手與結尾，支援 Uno 類裝置
def update_serial(port, firmware):
    try:
        with serial.Serial(port, 115200, timeout=10) as ser:
            print("送出 BEGIN")
            ser.write(b"BEGIN\n")
            time.sleep(1)
            print("傳送韌體資料...")
            ser.write(firmware)
            time.sleep(0.5)
            print("送出 END")
            ser.write(b"END\n")

            # 等待裝置回傳 OK 表示成功
            response = ser.read(64)
            print(f"裝置回應: {response}")
            return b"OK" in response
    except Exception as e:
        print(f"[Serial 更新錯誤] {e}")
        return False

# 主流程：部署到所有需要更新的裝置
def deploy_to_devices(customer_id, firmware_version):
    # 查詢特定 customer_id 和與 query 下來 firmware_version 不同的裝置，
    # 回傳 update_method、ip_address、manufacturer_id、device_type
    devices = get_devices_by_customer_and_version(customer_id, firmware_version)
    if not devices:
        print("找不到需要更新的裝置")
        return False
    
    # 負責針對每一個尚未更新的裝置進行韌體部署。它會根據裝置的更新方式（HTTPS 或 Serial）發送對應的韌體資料，
    # 然後根據結果回報成功或失敗，並更新資料庫中裝置的韌體版本狀態
    for dev in devices:
        method = dev["update_method"]
        addr = dev["ip_address"]
        manufacturer_id = dev["manufacturer_id"] 
        device_type = dev["device_type"]          
        print(f"開始通知 {addr}（{method}）更新至 {firmware_version}...")

        # 根據裝置更新方式呼叫對應子函式
        success = update_device(method=method, address=addr, firmware_version=firmware_version)
        # 如果成功，則更新資料庫中裝置的韌體版本狀態
        if success:
            print(f"{addr} 已通知更新（等待裝置回報）")
        else:
            print(f"{addr} 通知失敗")

    return True

# CLI 測試執行方式
if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("使用方式：python apply.py <customer_id> <firmware_version>")
        
    else:
        deploy_to_devices(sys.argv[1], sys.argv[2])
