from pathlib import Path
import sys
# thesis/
BASE_DIR = Path(__file__).resolve().parent.parent

# ==============================
# 加密演算法切換（唯一開關）
# ==============================
# True  → 使用 ECDSA (P-256)
# False → 使用 RSA (4096 bits)
USE_ECDSA = True

# ==============================
# Customer Agent 憑證目錄
# ==============================
CUSTOMER_AGENT_DIR  = BASE_DIR / "customer_agent"

# -------- 客戶端程式路徑 --------
CUSTOMER_REQUEST_PATH = CUSTOMER_AGENT_DIR / "customer_request.py"
APPLY_PATH = CUSTOMER_AGENT_DIR / "apply.py"

# ==============================
# 憑證與私鑰設定（依演算法切換）
# ==============================
if USE_ECDSA:
    # --- ECDSA ---
    SIGN_ALGORITHM = "ecdsa"

    CUSTOMER_KEY_PATH = CUSTOMER_AGENT_DIR  / "ecdsa_customer_private_key.pem"
    CUSTOMER_CERT_PATH = CUSTOMER_AGENT_DIR  / "ecdsa_customer_public_cert.pem"

    MANUFACTURER_AGENT_CERT_PATH = (
        CUSTOMER_AGENT_DIR  / "ecdsa_manufacturer_agent_public_cert.pem"
    )

else:
    # --- RSA ---
    SIGN_ALGORITHM = "rsa"

    CUSTOMER_KEY_PATH = CUSTOMER_AGENT_DIR  / "rsa_customer_private_key.pem"
    CUSTOMER_CERT_PATH = CUSTOMER_AGENT_DIR  / "rsa_customer_public_cert.pem"

    MANUFACTURER_AGENT_CERT_PATH = (
        CUSTOMER_AGENT_DIR  / "rsa_manufacturer_agent_public_cert.pem"
    )

MANUFACTURER_CERT_PATH = BASE_DIR / "ca" / "certs" / "ecdsa_manufacturer_ca_cert.pem"

# -------- CA 憑證 --------
CA_CERT_PATH = BASE_DIR / "ca" / "certs" / "ecdsa_ca.pem"
FULL_MANUFACTURER_CHAIN_CERT_PATH = BASE_DIR / "ca" / "certs" / "full_chain_manufacturer_client.pem"
FULL_CUSTOMER_CHAIN_CERT_PATH = BASE_DIR / "ca" / "certs" / "customer_fullchain.pem"
# -------- 上傳資料夾 --------
# UPLOAD_FOLDER = CUSTOMER_AGENT_DIR / "firmware_uploads"
# UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

# ======= Debug 檢查 =======
'''
for name, path in [
    ("CUSTOMER_KEY_PATH", CUSTOMER_KEY_PATH),
    ("CUSTOMER_CERT_PATH", CUSTOMER_CERT_PATH),
    ("MANUFACTURER_AGENT_CERT_PATH", MANUFACTURER_AGENT_CERT_PATH),
    ("MANUFACTURER_CERT_PATH", MANUFACTURER_CERT_PATH),
    ("CA_CERT_PATH", CA_CERT_PATH),
    ("FULL_MANUFACTURER_CHAIN_CERT_PATH", FULL_MANUFACTURER_CHAIN_CERT_PATH),
    ("FULL_CUSTOMER_CHAIN_CERT_PATH", FULL_CUSTOMER_CHAIN_CERT_PATH),
]:
    if not path.exists():
        print(f"[ERROR] 檔案不存在: {name} = {path}")
        sys.exit(1)
    else:
        print(f"[OK] 找到憑證: {name} = {path}")
'''