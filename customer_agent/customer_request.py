import requests
import base64
from verify import verify_signature, verify_response_signature
import sys
import json
from pathlib import Path
from db import get_firmware_metadata_by_customer_id, save_firmware_binary, get_firmware_signature_metadata, get_manufacturer_cert
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

# CLI 參數處理
# sys.argv[0]	執行的檔名 → customer_request.py
# sys.argv[1]	第一個參數 → customer_id
# sys.argv[2]	第二個參數 → firmware_version
if len(sys.argv) >= 3:
    customer_id = sys.argv[1]
    firmware_version = sys.argv[2]
else:
    print("請提供 customer_id 和 firmware_version")
    sys.exit(1)

# 憑證及私鑰路徑(用於 mTLS)
USE_ECDSA = True

if USE_ECDSA:
    CUSTOMER_PRIVATE_KEY_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_customer_private_key.pem")
    CUSTOMER_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_customer_public_cert.pem")
    MANUFACTURER_AGENT_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_manufacturer_agent_public_cert.pem")
    CA_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_ca.pem")
    SIGN_ALGO = "ecdsa"
else:
    CUSTOMER_PRIVATE_KEY_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/rsa_customer_private_key.pem")
    CUSTOMER_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/rsa_customer_public_cert.pem")
    MANUFACTURER_AGENT_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/manufacturer_agent_public_cert.pem")
    SIGN_ALGO = "rsa"

private_key = load_pem_private_key(CUSTOMER_PRIVATE_KEY_PATH.read_bytes(), password=None)

# 查詢 Metadata 
# get_firmware_metadata_by_customer_id 函式會透過 customer_id 查 customer_device 的資料表，
# 找出同樣 manufacturer + device_type 並且和 query 下來的 firmware_version 不同的所有 firmwaremetadata
firmware = get_firmware_metadata_by_customer_id(customer_id)
if not firmware:
    raise ValueError("找不到對應的 firmware metadata")

manufacturer_id = firmware["manufacturer_id"]
device_type = firmware["device_type"]

# 組合簽章內容，用於對 request payload 簽章，供 manufacturer_agent 驗證
request_raw = f"{manufacturer_id}{device_type}{firmware_version}{customer_id}".encode()

def sign(data):
    if USE_ECDSA:
        return base64.b64encode(private_key.sign(data, ec.ECDSA(hashes.SHA256()))).decode()
    else:
        return base64.b64encode(private_key.sign(data, padding.PKCS1v15(), hashes.SHA256())).decode()

# 傳送 Payload
payload = {
    "customer_id": customer_id,
    "manufacturer_id": manufacturer_id,
    "device_type": device_type,
    "firmware_version": firmware_version,
    "customer_signature_algorithm": SIGN_ALGO,
    "customer_signature": sign(request_raw),
}

# manufacturer_agent API 的 URL，回傳的 payload 中的 ResponseURL 欄位會在 URL 最後面帶一串 uuid
# 作為一次性 url
url = "https://localhost:8000/transfer_firmware/request_download/"

print(f"已開始下載韌體版本: {firmware_version}")

# 發送 POST 請求（使用 mTLS）######
response = requests.post(
    url,
    json=payload,
    cert=(str(CUSTOMER_CERT_PATH), str(CUSTOMER_PRIVATE_KEY_PATH)),
    verify=str(CA_CERT_PATH)
)
# print(" mTLS 成功連線")
print(f"[DEBUG] 狀態碼: {response.status_code}")
print(f"[DEBUG] 回應內容: {response.text}")
    
# 驗證回傳 payload 的 ManufacturerAgentSignature
if response.status_code in [200, 201]:

    response_json = json.loads(response.text)
    response_url = response_json.get("ResponseURL", "")
    message = response_json.get("Message", "")
    signature_b64 = response_json.get("ManufacturerAgentSignature", "")
    signature_algo = response_json.get("ManufacturerAgentSignatureAlgorithm", "")
    error_code = response_json.get("Errorcode", "")
    upload_result = response_json.get("ResponseResult", 0)



    cert_bytes = MANUFACTURER_AGENT_CERT_PATH.read_bytes()

    # 呼叫驗章函式
    if verify_response_signature(
        url=response_url,
        message=message,
        signature_b64=signature_b64,
        cert_bytes=cert_bytes,
        algorithm=signature_algo,
        error_code=error_code,
        upload_result=upload_result
    ):
        # print("簽章驗證成功")
            
        # 發送 firmware_data 下載請求
        firmware_response = requests.get(response_url, cert=(str(CUSTOMER_CERT_PATH), str(CUSTOMER_PRIVATE_KEY_PATH)), verify=str(CA_CERT_PATH))#####
        if firmware_response.status_code == 200:
            firmware_binary = firmware_response.content
    
            # 取得該版本 metadata 資料，使用 firmware_signature 驗證下載來的 firmware_data
            metadata = get_firmware_signature_metadata(manufacturer_id, device_type, firmware_version)
            if not metadata:
                print("查無該版本 firmware metadata，無法驗章")
                sys.exit(1)

            # 解析 signature（BLOB 為 bytes）
            firmware_signature = metadata["firmware_signature"]
            # 取得該 manufacturer 的憑證
            cert_bytes = get_manufacturer_cert(manufacturer_id)
                
            # 驗章
            if verify_signature(metadata, cert_bytes, "firmware_signature", firmware_signature, firmware_binary):
                # 驗證成功後存入 db
                save_firmware_binary(manufacturer_id, device_type, firmware_version, firmware_binary)
                print(f"已成功下載並儲存韌體版本: {firmware_version}")
            else:
                print("韌體簽章驗證失敗，不儲存")
                sys.exit(1)
        else:
            print(f"韌體下載失敗: {firmware_response.status_code}", file=sys.stderr)
            sys.exit(1)
            
else:
    # 錯誤時印出錯誤訊息並結束
    try:
        resp_json = response.json()
        print(f"[ERROR] 錯誤代碼: {resp_json.get('Errorcode')}", file=sys.stderr)
        print(f"[ERROR] 錯誤訊息: {resp_json.get('Message')}", file=sys.stderr)
    except Exception:
        print("[ERROR] 無法解析 JSON 錯誤內容", file=sys.stderr)
    sys.exit(1)
    
'''   
except requests.exceptions.SSLError as e:
    print(" TLS 錯誤:", e)
except Exception as e:
    print(" 發送失敗:", e)
    import traceback
    traceback.print_exc(file=sys.stderr)  # 關鍵：寫入 stderr
    sys.exit(1)
'''