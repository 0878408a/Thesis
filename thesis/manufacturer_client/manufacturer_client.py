import requests
import base64
import datetime
import json
import sys
from pathlib import Path
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

sys.path.append(str(Path(__file__).resolve().parents[1]))
# --- 引入 config ---
from shared.config import (
    USE_ECDSA,
    MANUFACTURER_PRIVATE_KEY_PATH,
    MANUFACTURER_CERT_PATH,
    CA_CERT_PATH,
    SIGN_ALGO,
    UPLOAD_URL,
    FIRMWARE_PATH_BLINK,
    FIRMWARE_PATH_NO_BLINK,
    MANUFACTURER_ID,
    DEVICE_TYPE,
    FIRMWARE_VERSION
)
    
# 載入私鑰
private_key = load_pem_private_key(MANUFACTURER_PRIVATE_KEY_PATH.read_bytes(), password=None)

# Django API 的 URL（請依實際路徑調整）
url = "https://localhost:8000/upload_firmware/upload/"

# 註冊 ngrok 指令: curl -X POST "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=<NGROK_HTTPS_URL>/webhook"


# 建立測試資料
test_firmware = FIRMWARE_PATH_BLINK.read_bytes() # 可依測試需求替換成 FIRMWARE_PATH_BLINK 或 FIRMWARE_PATH_BLINK_FAST
firmware_size = len(test_firmware)
firmware_b64 = base64.b64encode(test_firmware).decode()

# 取得目前時間的 release_date（NTP timestamp）
release_date = int((datetime.datetime.now(datetime.timezone.utc) - datetime.datetime(1900, 1, 1, tzinfo=datetime.timezone.utc)).total_seconds())
# print("release_date:", release_date)

# 組合 metadata 簽章原始資料
metadata_raw = f"{firmware_size}{release_date}{MANUFACTURER_ID}{DEVICE_TYPE}{FIRMWARE_VERSION}".encode()

# 簽章函式
# 傳入值: bytes 回傳值: str
def sign(data: bytes) -> str:
    
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
        "manufacturer_id": MANUFACTURER_ID,
        "device_type": DEVICE_TYPE,
        "firmware_version": FIRMWARE_VERSION
    }
}

print("POST 傳送的 JSON 結構:")
print(json.dumps(payload["metadata"], indent=2))

# 發送 POST 請求（使用 mTLS）
try:
    response = requests.post(
        UPLOAD_URL,
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
