# thesis/config.py
import os
from pathlib import Path

# =========================================================
# BASE DIRECTORY
# =========================================================

# 指向 thesis/，若只有一個 .parant 是指向當前的 /shared 資料夾
BASE_DIR = Path(__file__).resolve().parent.parent

# 子目錄
CA_DIR = BASE_DIR / "ca" / "certs"
MANUFACTURER_AGENT_DIR = BASE_DIR / "manufacturer_agent"
MANUFACTURER_CLIENT_DIR = BASE_DIR / "manufacturer_client"
CUSTOMER_AGENT_DIR = BASE_DIR / "customer_agent"

# =========================================================
# CRYPTO SETTINGS
# =========================================================

USE_ECDSA = True  # False → 使用 RSA

if USE_ECDSA:
    SIGN_ALGO = "ecdsa"
    CA_CERT_PATH = CA_DIR / "ecdsa_ca.pem"
else:
    SIGN_ALGO = "rsa"
    CA_CERT_PATH = CA_DIR / "ca.pem"

FULL_CHAIN_CERT_PATH = CA_DIR / "full_chain_manufacturer_agent.pem"

# =========================================================
# MANUFACTURER CLIENT
# =========================================================

if USE_ECDSA:
    MANUFACTURER_PRIVATE_KEY_PATH = MANUFACTURER_CLIENT_DIR / "ecdsa_manufacturer_private_key.pem"
    MANUFACTURER_CERT_PATH = MANUFACTURER_CLIENT_DIR / "ecdsa_manufacturer_client_cert.pem"
else:
    MANUFACTURER_PRIVATE_KEY_PATH = MANUFACTURER_CLIENT_DIR / "manufacturer_private_key.pem"
    MANUFACTURER_CERT_PATH = MANUFACTURER_CLIENT_DIR / "manufacturer_public_cert.pem"

# =========================================================
# MANUFACTURER AGENT 
# =========================================================

if USE_ECDSA:
    MANUFACTURER_AGENT_PRIVATE_KEY_PATH = MANUFACTURER_AGENT_DIR / "ecdsa_manufacturer_agent_private_key.pem"
    MANUFACTURER_AGENT_CERT_PATH = MANUFACTURER_AGENT_DIR / "ecdsa_manufacturer_agent_public_cert.pem"
else:
    MANUFACTURER_AGENT_PRIVATE_KEY_PATH = MANUFACTURER_AGENT_DIR / "manufacturer_agent_private_key.pem"
    MANUFACTURER_AGENT_CERT_PATH = MANUFACTURER_AGENT_DIR / "manufacturer_agent_public_cert.pem"

# =========================================================
# CUSTOMER AGENT
# =========================================================

if USE_ECDSA:
    CUSTOMER_PRIVATE_KEY_PATH = CUSTOMER_AGENT_DIR / "ecdsa_customer_private_key.pem"
    CUSTOMER_CERT_PATH = CUSTOMER_AGENT_DIR / "ecdsa_customer_public_cert.pem"
else:
    CUSTOMER_PRIVATE_KEY_PATH = CUSTOMER_AGENT_DIR / "rsa_customer_private_key.pem"
    CUSTOMER_CERT_PATH = CUSTOMER_AGENT_DIR / "rsa_customer_public_cert.pem"

# =========================================================
# FIRMWARE PATHS (manufacturer_client 使用)
# =========================================================

FIRMWARE_PATH_BLINK = MANUFACTURER_CLIENT_DIR / "blink.ino" / "blink.ino.bin"
FIRMWARE_PATH_NO_BLINK = MANUFACTURER_CLIENT_DIR / "no_blink.ino" / "no_blink_ino.bin"

# ============================================================================
# 環境變數覆蓋 (Docker / 部署)
# ----------------------------------------------------------------------------
# 下列環境變數可用於覆蓋憑證/金鑰路徑, 讓容器可以從 volume mount 取得
# 憑證, 而不需要把 private key bake 進 image。
# 預設值為原始硬編碼路徑, 因此既有 host 開發行為完全不變。
#   CERT_DIR  : 若設定, 所有憑證/金鑰路徑改指到此目錄
# ============================================================================
_CERT_DIR_OVERRIDE = os.getenv("CERT_DIR")

if _CERT_DIR_OVERRIDE:
    _cd = Path(_CERT_DIR_OVERRIDE)
    CA_CERT_PATH = _cd / "ecdsa_ca.pem"
    MANUFACTURER_PRIVATE_KEY_PATH = _cd / "ecdsa_manufacturer_private_key.pem"
    MANUFACTURER_CERT_PATH = _cd / "ecdsa_manufacturer_client_cert.pem"
    MANUFACTURER_AGENT_PRIVATE_KEY_PATH = _cd / "ecdsa_manufacturer_agent_private_key.pem"
    MANUFACTURER_AGENT_CERT_PATH = _cd / "ecdsa_manufacturer_agent_public_cert.pem"
    CUSTOMER_PRIVATE_KEY_PATH = _cd / "ecdsa_customer_private_key.pem"
    CUSTOMER_CERT_PATH = _cd / "ecdsa_customer_public_cert.pem"
    FULL_CHAIN_CERT_PATH = _cd / "full_chain_manufacturer_agent.pem"

# =========================================================
# API SETTINGS
# =========================================================

HOST = "0.0.0.0"
PORT = 8000
# UPLOAD_URL / HISTORY_URL 支援環境變數覆蓋 (Docker 部署時指向 nginx mTLS 端點):
#   UPLOAD_URL  : 預設 https://localhost/upload_firmware/upload/
#   HISTORY_URL : 預設 https://localhost/upload_firmware/history/
# 未設定時保留原 host 開發行為; Docker compose 中由 env 覆蓋。
UPLOAD_URL = os.environ.get(
    "UPLOAD_URL",
    f"https://localhost:8443/upload_firmware/upload/",
)
HISTORY_URL = os.environ.get(
    "HISTORY_URL",
    f"https://localhost:8443/upload_firmware/history/",
)

# =========================================================
# BLOCKCHAIN SCRIPT (manufacturer_agent 使用)
# =========================================================

SUBMIT_FIRMWARE_TS_PATH = MANUFACTURER_AGENT_DIR / "upload_firmware" / "submit_firmware.ts"

# =========================================================
# METADATA
# =========================================================

MANUFACTURER_ID = "123e4567-e89b-12d3-a456-426614174000"
DEVICE_TYPE = "esp32"
FIRMWARE_VERSION = "v0.0.2"