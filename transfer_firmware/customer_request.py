import requests
import base64
import os
from pathlib import Path
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

USE_ECDSA = True  # 改成 False 即可改用 RSA 簽章測試

if USE_ECDSA:
    
    # 使用 NIST P-256 標準生成，金鑰長度 256 bits，強度等於 RSA 3072 bits
    CUSTOMER_PRIVATE_KEY_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_customer_private_key.pem")
    CUSTOMER_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_customer_public_cert.pem")
    # MANUFACTURER_AGENT_PRIVATE_KEY_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_manufacturer_agent_private_key.pem")
    CA_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_ca.pem")
    SIGN_ALGO = "ecdsa"

else:
    
    # 使用 RSA 4096 bits 生成
    CUSTOMER_PRIVATE_KEY_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/rsa_customer_private_key.pem")
    CUSTOMER_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/rsa_customer_public_cert.pem")
    # MANUFACTURER_AGENT_PRIVATE_KEY_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/manufacturer_agent_private_key.pem")
    MANUFACTURER_AGENT_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/manufacturer_agent_public_cert.pem")
    SIGN_ALGO = "rsa"
    
# 載入私鑰
private_key = load_pem_private_key(CUSTOMER_PRIVATE_KEY_PATH.read_bytes(), password=None)

# Django API 的 URL（請依實際路徑調整）
url = "https://localhost:8000/transfer_firmware/request_download/"

# 建立測試資料
# 資料庫已有的 manufacturer_id、customer_id
customer_id = "3e01e6a7-1c25-4a5e-97c5-92ec5abfd10c"
manufacturer_id = "123e4567-e89b-12d3-a456-426614174000"
device_type = "esp32"
firmware_version = "v1.0"

# 組合 request 簽章原始資料
request_raw = f"{manufacturer_id}{device_type}{firmware_version}{customer_id}".encode()

### 未來加入: 先驗回傳的簽章，再透過 url 下載韌體 ###
# 簽章函式
# 傳入值: bytes 回傳值: str
def sign(data):
    
    if USE_ECDSA:
        signature = private_key.sign(data, ec.ECDSA(hashes.SHA256()))
    else:
        signature = private_key.sign(data, padding.PKCS1v15(), hashes.SHA256())
    
    return base64.b64encode(signature).decode()

# POST 傳送的 JSON 結構
payload = {
    "customer_id": customer_id,
    "manufacturer_id": manufacturer_id,
    "device_type": device_type,
    "firmware_version": firmware_version,
    "customer_signature_algorithm": SIGN_ALGO,
    "customer_signature": sign(request_raw),
}


# 發送 POST 請求（使用 mTLS）
try:
    response = requests.post(
        url,
        # 自動加入 Content-Type: application/json
        json=payload,  
        # 在 mTLS（雙向 TLS）驗證中使用正確的「客戶端憑證與私鑰」來發送 HTTPS 請求。
        cert=(str(CUSTOMER_CERT_PATH), str(CUSTOMER_PRIVATE_KEY_PATH)),
        verify=str(CA_CERT_PATH) 
    )
    print(" 成功建立 mTLS 連線")    
    print(" 狀態碼:", response.status_code)
    print(" 回應內容:", response.text)

    response_data = response.json()
    download_url = response_data.get("ResponseURL")

    # 嘗試下載韌體
    if response_data.get("ResponseResult") == 1 and download_url:
        print(f"\n嘗試下載韌體: {download_url}\n")
        download_response = requests.get(
            download_url,
            cert=(str(CUSTOMER_CERT_PATH), str(CUSTOMER_PRIVATE_KEY_PATH)),
            verify=str(CA_CERT_PATH),
            stream=True
        )

        if download_response.status_code == 200:
            firmware_path = Path("downloaded_firmware.bin")
            with open(firmware_path, "wb") as f:
                for chunk in download_response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print("成功下載韌體並儲存至：", firmware_path)

        else:
            print(f"下載失敗，狀態碼: {download_response.status_code}")
            print(download_response.text)
    else:
        print("ResponseURL 無效或回應結果失敗")

except requests.exceptions.SSLError as e:
    print("TLS/mTLS 錯誤:", e)

except Exception as e:
    print("其他錯誤:", e)

