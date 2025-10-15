import os
import sys
import ssl
from pathlib import Path

# 加入專案目錄到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# 設定 Django 專案設定檔
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Manufacturer_Client.settings")  # 修改為自己的 Django 專案名稱

from django.core.wsgi import get_wsgi_application
from werkzeug.serving import run_simple

# 憑證與私鑰路徑
MANUFACTURER_AGENT_PRIVATE_KEY_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_manufacturer_agent_private_key.pem")
FULL_CHAIN_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/full_chain.pem")
CA_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_ca.pem")

'''
    註冊 webhook 至 ngrok 指令:
    curl -X POST "https://api.telegram.org/botREMOVED/setWebhook?url=https://你的-ngrok-url/webhook"
    
    WSL mTLS curl 測試指令:cd /mnt/c/users/user/Downloads/ray/manufacturer_agent
    curl -v https://localhost:8000/upload_firmware/upload/   --cert ecdsa_manufacturer_public_cert.pem   --key ecdsa_manufacturer_private_key.pem   --cacert ecdsa_ca.pem
    curl -v https://localhost:8000/transfer_firmware/request_download/   --cert ecdsa_customer_public_cert.pem   --key  ecdsa_customer_private_key.pem   --cacert ecdsa_ca.pem
'''

# 建立 SSL context（mTLS）
context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
context.load_cert_chain(certfile=str(FULL_CHAIN_CERT_PATH), keyfile=str(MANUFACTURER_AGENT_PRIVATE_KEY_PATH))
context.load_verify_locations(cafile=str(CA_CERT_PATH))
context.verify_mode = ssl.CERT_REQUIRED

# 啟動 Django with Werkzeug + SSL
application = get_wsgi_application()
run_simple(
    hostname="0.0.0.0",
    port=8000,
    application=application,
    ssl_context=context
)
