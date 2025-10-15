import requests
import serial
import time
from pathlib import Path
from db import get_devices_by_customer_and_version, get_firmware_by_version, mark_device_updated

# 憑證與私鑰路徑
CUSTOMER_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_customer_public_cert.pem")
CUSTOMER_KEY_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_customer_private_key.pem")
# DEVICE_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/esp32_device_cert.pem")

# 根據更新方式呼叫對應子函式
def update_device(method, address, firmware_bytes):
    if method == "http":
        return update_http(address, firmware_bytes)
    elif method == "serial":
        return update_serial(address, firmware_bytes)
    else:
        print(f"不支援的更新方式: {method}")
        return False

# HTTP 傳送（使用 mTLS）
def update_http(ip, firmware):
    try:
        url = f"http://{ip}/update"
        # 模擬上傳檔案行為，因為 ESP32 OTA firmware 要求
        # application/octet-stream 表示任意二進位資料流，用於傳送 .bin、.exe、韌體等原始檔案
        files = {
            "firmware": ("firmware.bin", firmware, "application/octet-stream")
        }######效能問題??
        resp = requests.post(url, files=files, timeout=30)
        print(f"[HTTP 回應] {resp.status_code} - {resp.text}")
        return resp.status_code == 200
    except Exception as e:
        print(f"[HTTP 更新錯誤] {e}")
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
    
    # 根據 firmware_version 取出 firmware_data（韌體本體）
    firmware_row = get_firmware_by_version(firmware_version)
    if not firmware_row or not firmware_row["firmware_data"]:
        print("找不到對應的韌體資料")
        return False
    
    '''
        # 儲存 firmware bin 檔案到本地（供驗證使用）
        import os
        output_dir = "C:/Users/User/Downloads/ray/manufacturer_agent/customer_agent"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"firmware_{firmware_version}.bin")

        with open(output_path, "wb") as f:
            f.write(firmware_row["firmware_data"])
        print(f"[DEBUG] 已儲存韌體檔案至: {output_path}")
    '''
    
    firmware_bytes = firmware_row["firmware_data"]
    # 負責針對每一個尚未更新的裝置進行韌體部署。它會根據裝置的更新方式（HTTP 或 Serial）發送對應的韌體資料，
    # 然後根據結果回報成功或失敗，並更新資料庫中裝置的韌體版本狀態
    for dev in devices:
        method = dev["update_method"]
        addr = dev["ip_address"]
        manufacturer_id = dev["manufacturer_id"] 
        device_type = dev["device_type"]          
        print(f"開始部署至 {addr}（{method}）...")

        # 根據裝置更新方式呼叫對應子函式
        success = update_device(method=method, address=addr, firmware_bytes=firmware_bytes)
        # 如果成功，則更新資料庫中裝置的韌體版本狀態
        if success:
            mark_device_updated(customer_id, manufacturer_id, device_type, firmware_version)
            print(f"{addr} 成功（版本已更新為 {firmware_version}）")
        else:
            print(f"{addr} 失敗")

    return True

# CLI 測試執行方式
if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("使用方式：python apply.py <customer_id> <firmware_version>")
        
    else:
        deploy_to_devices(sys.argv[1], sys.argv[2])
