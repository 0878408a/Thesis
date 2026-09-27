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
    HISTORY_URL,
    FIRMWARE_PATH_BLINK,
    FIRMWARE_PATH_NO_BLINK,
    MANUFACTURER_ID,
    DEVICE_TYPE,
    FIRMWARE_VERSION
)

# 註冊 ngrok 指令: curl -X POST "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=<NGROK_HTTPS_URL>/webhook"


def load_private_key():
    """載入私鑰，僅保留在 Manufacturer Client 內部。"""
    return load_pem_private_key(MANUFACTURER_PRIVATE_KEY_PATH.read_bytes(), password=None)


def sign(data: bytes) -> str:
    """使用目前既有的簽章邏輯產生 Base64 簽章。"""
    private_key = load_private_key()

    if USE_ECDSA:
        signature = private_key.sign(data, ec.ECDSA(hashes.SHA256()))
    else:
        signature = private_key.sign(data, padding.PKCS1v15(), hashes.SHA256())

    return base64.b64encode(signature).decode()


def build_upload_payload(firmware_bytes: bytes, firmware_version: str, device_type: str):
    """依照目前既有流程組裝 upload payload，保留 original signing 和 metadata structure。"""
    firmware_size = len(firmware_bytes)
    firmware_b64 = base64.b64encode(firmware_bytes).decode()

    release_date = int(
        (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.datetime(1900, 1, 1, tzinfo=datetime.timezone.utc)
        ).total_seconds()
    )

    metadata_raw = (
        f"{firmware_size}{release_date}{MANUFACTURER_ID}{device_type}{firmware_version}".encode()
    )

    payload = {
        "firmware_data": firmware_b64,
        "metadata": {
            "metadata_signature_algorithm": SIGN_ALGO,
            "metadata_signature": sign(metadata_raw),
            "firmware_signature_algorithm": SIGN_ALGO,
            "firmware_signature": sign(firmware_bytes),
            "firmware_size": firmware_size,
            "release_date": release_date,
            "manufacturer_id": MANUFACTURER_ID,
            "device_type": device_type,
            "firmware_version": firmware_version,
        },
    }

    return payload


def upload_with_mtls(payload):
    """使用 mTLS 路徑對 Django Upload API 發送目前既有的 payload。"""
    return requests.post(
        UPLOAD_URL,
        json=payload,
        cert=(str(MANUFACTURER_CERT_PATH), str(MANUFACTURER_PRIVATE_KEY_PATH)),
        verify=str(CA_CERT_PATH),
    )

def history_with_mtls(page: str = "1"):
    """使用 Manufacturer Client 的 mTLS 憑證取得 Firmware History。"""

    return requests.get(
        HISTORY_URL,
        params={"page": page},
        cert=(
            str(MANUFACTURER_CERT_PATH),
            str(MANUFACTURER_PRIVATE_KEY_PATH),
        ),
        verify=str(CA_CERT_PATH),
    )

def main():
    """保留原始 CLI 行為：直接使用預設 firmware 檔案發送 upload request。"""
    test_firmware = FIRMWARE_PATH_BLINK.read_bytes()
    payload = build_upload_payload(test_firmware, FIRMWARE_VERSION, DEVICE_TYPE)

    print("POST 傳送的 JSON 結構:")
    print(json.dumps(payload["metadata"], indent=2))

    try:
        response = upload_with_mtls(payload)
        print(" 成功建立 mTLS 連線")
        print(" 狀態碼:", response.status_code)
        print(" 回應內容:", response.text)

    except requests.exceptions.SSLError as e:
        print(" TLS/mTLS 錯誤:", e)

    except Exception as e:
        print(" 其他錯誤:", e)


if __name__ == "__main__":
    main()
