import requests
import base64
import datetime
import json
from pathlib import Path
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

USE_ECDSA = True  # 改成 False 即可改用 RSA 簽章測試

if USE_ECDSA:
    
    # 使用 NIST P-256 標準生成，金鑰長度 256 bits，強度等於 RSA 3072 bits
    MANUFACTURER_PRIVATE_KEY_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_manufacturer_private_key.pem")
    MANUFACTURER_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_manufacturer_public_cert.pem")
    CA_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_ca.pem")
    SIGN_ALGO = "ecdsa"
    
else:
    
    # 使用 RSA 4096 bits 生成
    MANUFACTURER_PRIVATE_KEY_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/manufacturer_private_key.pem")
    MANUFACTURER_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/manufacturer_public_cert.pem")
    MANUFACTURER_AGENT_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/manufacturer_agent_public_cert.pem")
    SIGN_ALGO = "rsa"
    
# 載入私鑰
private_key = load_pem_private_key(MANUFACTURER_PRIVATE_KEY_PATH.read_bytes(), password=None)

# Django API 的 URL（請依實際路徑調整）
url = "https://localhost:8000/upload_firmware/upload/"

# 註冊 ngrok 指令: curl -X POST "https://api.telegram.org/botREMOVED/setWebhook?url=https://2db6-2001-b400-e75d-7c78-8170-b4c3-9ec3-c63.ngrok-free.app/webhook"

# 韌體路徑（可換成你的實際檔案）
FIRMWARE_PATH_BLINK = Path("C:/Users/User/Downloads/ray/manufacturer_agent/Manufacturer_Client/blink.ino/blink.ino.ino.node32s.bin")
FIRMWARE_PATH_BLINK_FAST = Path("C:/Users/User/Downloads/ray/manufacturer_agent/Manufacturer_Client/blink_fast.ino/blink_fast.ino.ino.node32s.bin")
FIRMWARE_PATH_NO_BLINK = Path("C:/Users/User/Downloads/ray/manufacturer_agent/Manufacturer_Client/no_blink.ino/no_blink.ino.node32s.bin")

# 建立測試資料
test_firmware = FIRMWARE_PATH_BLINK.read_bytes()
firmware_size = len(test_firmware)
firmware_b64 = base64.b64encode(test_firmware).decode()

# 取得目前時間的 release_date（NTP timestamp）
release_date = int((datetime.datetime.now(datetime.timezone.utc) - datetime.datetime(1900, 1, 1, tzinfo=datetime.timezone.utc)).total_seconds())
# print("release_date:", release_date)

# 資料庫已有的 manufacturer_id
manufacturer_id = "123e4567-e89b-12d3-a456-426614174000"
device_type = "esp32"
firmware_version = "v1.13"

# 組合 metadata 簽章原始資料
metadata_raw = f"{firmware_size}{release_date}{manufacturer_id}{device_type}{firmware_version}".encode()

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
    "firmware_data": firmware_b64,
    "metadata": {
        "metadata_signature_algorithm": SIGN_ALGO,
        "metadata_signature": sign(metadata_raw),
        "firmware_signature_algorithm": SIGN_ALGO,
        "firmware_signature": sign(test_firmware),
        "firmware_size": firmware_size,
        "release_date": release_date,
        "manufacturer_id": manufacturer_id,
        "device_type": device_type,
        "firmware_version": firmware_version
    }
}
print("POST 傳送的 JSON 結構:")
print(json.dumps(payload["metadata"], indent=2))

# 發送 POST 請求（使用 mTLS）
try:
    response = requests.post(
        url,
        # 自動加入 Content-Type: application/json
        json=payload,  
        # 在 mTLS（雙向 TLS）驗證中使用正確的「客戶端憑證與私鑰」來發送 HTTPS 請求。
        cert=(str(MANUFACTURER_CERT_PATH), str(MANUFACTURER_PRIVATE_KEY_PATH)),
        verify=str(CA_CERT_PATH) 
    )
    print(" 成功建立 mTLS 連線")    
    print(" 狀態碼:", response.status_code)
    print(" 回應內容:", response.text)

except requests.exceptions.SSLError as e:
    print(" TLS/mTLS 錯誤:", e)

except Exception as e:
    print(" 其他錯誤:", e)
