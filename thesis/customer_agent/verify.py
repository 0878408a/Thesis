import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, ec
from cryptography.x509 import load_pem_x509_certificate

# 支援的演算法對照表
SUPPORTED_SIGNATURE_ALGORITHMS = {
    "rsa": "RSA",
    "rsa-4096": "RSA",
    "rsa4096": "RSA",
    "rsa_pkcs1_sha256": "RSA",
    "rsa-sha256": "RSA",
    "rsassa-pkcs1-v1_5": "RSA",

    "ecdsa": "ECDSA",
    "ecdsa-secp256r1": "ECDSA",
    "ecdsa-sha256": "ECDSA",
    "ecdsa-with-sha256": "ECDSA",
    "ecdsa-p256": "ECDSA",
    "es256": "ECDSA"
}

# 函式 verify_signature() 定義: 驗證簽章欄位（使用 Base64 編碼）
# firmware_binary=None 參數預設為 None，若要驗證韌體簽章才需要傳入 firmware_binary
def verify_signature(metadata_json, manufacturer_cert, signature_field, signature_bytes, firmware_binary=None):
    try:
        # 組合簽章原始資料
        # 根據是驗哪一種簽章來決定要組合哪種 raw_data
        if signature_field == "metadata_signature":
            raw_data = f"{metadata_json['firmware_size']}{metadata_json['release_date']}{metadata_json['manufacturer_id']}{metadata_json['device_type']}{metadata_json['firmware_version']}".encode()
            algo = metadata_json.get("metadata_signature_algorithm", "").lower()
        elif signature_field == "firmware_signature":
            raw_data = firmware_binary
            algo = metadata_json.get("firmware_signature_algorithm", "").lower()
        else:
            print("[驗章失敗] 不支援的 signature_field")
            return False

        # 憑證從 hex 字串轉回 bytes
        if isinstance(manufacturer_cert, str):
            if manufacturer_cert.startswith("0x"):
                # 如果憑證是以 "0x" 開頭，則去掉前綴並轉換為 bytes
                manufacturer_cert = bytes.fromhex(manufacturer_cert[2:])
            else:
                manufacturer_cert = manufacturer_cert.encode()

        # 從憑證中取出公鑰
        # load_pem_x509_certificate() 是 cryptography 函式庫提供的工具，
        # 傳入的參數必須是 bytes 型別（不是 string，要 .encode()）；
        # 解析後，cert 會是一個 x509.Certificate 物件
        cert = load_pem_x509_certificate(manufacturer_cert)
        public_key = cert.public_key()
        
        # 使用正確的驗章演算法
        if SUPPORTED_SIGNATURE_ALGORITHMS.get(algo) == "RSA":
            public_key.verify(signature_bytes, raw_data, padding.PKCS1v15(), hashes.SHA256())

        elif SUPPORTED_SIGNATURE_ALGORITHMS.get(algo) == "ECDSA":
            public_key.verify(signature_bytes, raw_data, ec.ECDSA(hashes.SHA256()))

        else:
            print(f"[驗章失敗] 不支援的演算法: {algo}")
            return False

        return True

    except Exception as e:
        print(f"[DEBUG] Signature verification failed: {e}")
        return False

# 函式 verify_response_signature() 定義: 驗證回應簽章欄位（使用 Base64 編碼）
def verify_response_signature(url, message, signature_b64, cert_bytes, algorithm, error_code=None, upload_result=1):
    try:
        # 組合簽章原始資料
        # raw_payload = f"{upload_result}|{url}|{message}|{error_code}".encode()
        err_str = str(error_code) if error_code is not None else ""
        url_str = url if url else ""
        raw_payload = f"{upload_result}|{url_str}|{message}|{err_str}".encode()

        signature = base64.b64decode(signature_b64)
        cert = load_pem_x509_certificate(cert_bytes)
        public_key = cert.public_key()

        if "rsa" in algorithm.lower():
            public_key.verify(signature, raw_payload, padding.PKCS1v15(), hashes.SHA256())
        elif "ecdsa" in algorithm.lower():
            public_key.verify(signature, raw_payload, ec.ECDSA(hashes.SHA256()))
        else:
            print(f"[驗章失敗] 不支援的演算法: {algorithm}")
            return False

        return True

    except Exception as e:
        print("[驗章失敗] Exception:", e)
        return False
