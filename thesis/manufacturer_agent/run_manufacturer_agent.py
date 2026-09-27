import os
import ssl
import sys
from pathlib import Path

# 加入專案目錄到 sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# 設定 Django 專案
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

from django import setup as django_setup
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application
from werkzeug.serving import run_simple

from shared.config import HOST, PORT

# ENABLE_MTLS=1 啟用 mTLS（本機直接測試時用）；預設 plain HTTP（Docker/nginx 用）
_ENABLE_MTLS = os.environ.get("ENABLE_MTLS", "0") == "1"


def main():
    if _ENABLE_MTLS:
        from shared.config import (
            MANUFACTURER_AGENT_PRIVATE_KEY_PATH,
            MANUFACTURER_AGENT_CERT_PATH,
            CA_CERT_PATH,
        )
        print("Starting Manufacturer Agent (mTLS)")
        print(f"Listening on https://{HOST}:{PORT}")
        print(f"CA: {CA_CERT_PATH}")

        def create_ssl_context():
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            context.load_cert_chain(
                certfile=str(MANUFACTURER_AGENT_CERT_PATH),
                keyfile=str(MANUFACTURER_AGENT_PRIVATE_KEY_PATH),
            )
            context.load_verify_locations(cafile=str(CA_CERT_PATH))
            context.verify_mode = ssl.CERT_REQUIRED
            return context

        django_setup()
        call_command("migrate", run_syncdb=True, verbosity=0, interactive=False)
        application = get_wsgi_application()
        run_simple(
            hostname=HOST,
            port=PORT,
            application=application,
            ssl_context=create_ssl_context(),
        )
    else:
        print("Starting Manufacturer Agent (plain HTTP)")
        print(f"Listening on http://{HOST}:{PORT}")
        django_setup()
        call_command("migrate", run_syncdb=True, verbosity=0, interactive=False)
        application = get_wsgi_application()
        run_simple(
            hostname=HOST,
            port=PORT,
            application=application,
        )


if __name__ == "__main__":
    main()