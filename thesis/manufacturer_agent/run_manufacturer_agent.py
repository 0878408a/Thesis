import os
import sys
import ssl
from pathlib import Path

'''
    因 django 無法支援 mTLS，所以得另外使用Werkzeug，來透過自簽憑證啟動測試用 server
'''

# 加入專案目錄到 sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# 設定 Django 專案設定檔
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")  # 修改為自己的 Django 專案名稱

from django.core.wsgi import get_wsgi_application
from werkzeug.serving import run_simple

'''
    Werkzeug 用 OpenSSL 直接啟動 mTLS server 時，必須明確提供「完整憑證鏈（full chain）」給 client，
    且 ca 憑證為實驗模擬的自簽憑證，client不認得，除非是公有 CA（Let's Encrypt 等）
    已經預先存在 Client OS / Browser 的 trust store 才會被預設信任。
'''

# imort 憑證與私鑰路徑
from shared.config import (
    MANUFACTURER_AGENT_PRIVATE_KEY_PATH,
    MANUFACTURER_AGENT_CERT_PATH,
    CA_CERT_PATH,
    HOST,
    PORT,
)

'''
    註冊 webhook 至 ngrok 指令:
    curl -X POST "https://api.telegram.org/<BOT_TOKEN>/setWebhook?url=/<NGROK_URL>/webhook"
    
    WSL mTLS curl 測試指令:cd /mnt/c/users/user/Downloads/ray/manufacturer_agent
    curl -v https://localhost:8000/upload_firmware/upload/   --cert ecdsa_manufacturer_public_cert.pem   --key ecdsa_manufacturer_private_key.pem   --cacert ecdsa_ca.pem
    curl -v https://localhost:8000/transfer_firmware/request_download/   --cert ecdsa_customer_public_cert.pem   --key  ecdsa_customer_private_key.pem   --cacert ecdsa_ca.pem
'''

# 建立 SSL context（mTLS）
def create_ssl_context():
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

    context.load_cert_chain(
        certfile=str(MANUFACTURER_AGENT_CERT_PATH),
        keyfile=str(MANUFACTURER_AGENT_PRIVATE_KEY_PATH),
    )

    context.load_verify_locations(
        cafile=str(CA_CERT_PATH)
    )

    context.verify_mode = ssl.CERT_REQUIRED
    return context

# 啟動 Django with Werkzeug + SSL
def main():
    print(" Starting Manufacturer Agent (mTLS)")
    print(" CA:", CA_CERT_PATH)
    print(" Manufacturer Agent Cert:", MANUFACTURER_AGENT_CERT_PATH)

    context = create_ssl_context()
    application = get_wsgi_application()

    run_simple(
        hostname=HOST,
        port=PORT,
        application=application,
        ssl_context=context,
    )

if __name__ == "__main__":
    main()
