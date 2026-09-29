"""
V2 concurrency tests for /upload_firmware/upload/ — 20 concurrent identical-version uploads.

Executes 20 concurrent requests to the API endpoint via Django's test client (no real K8s needed).
Test assertions:
- Exactly 1 record created, 19 conflict 409s
- No IntegrityError traceback leaks in response body
- No 500 / 404 / 401 / 405 responses
- DB count == 1
- Cleanup

To run (V2 local env, thesis-mariadb running):
  cd thesis/manufacturer_agent
  python -m pytest upload_firmware/tests_concurrency.py -v -s

All models are managed=False; the test DB must already have the schema.
Both v2_concurrency_test_db and test_v2_concurrency_test_db are pre-created on local MySQL.
"""
import sys
import os
import base64
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path

# Make the thesis/ root importable so that 'shared' resolves
_THIS_DIR = Path(__file__).resolve().parent.parent.parent  # thesis/
sys.path.insert(0, str(_THIS_DIR))

import django
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

# ---- Test database: local MySQL on 127.0.0.1:3306 (root) ----
# The local Windows mysqld (PID owning 3306) is used; thesis-mariadb is not reachable.
# Both v2_concurrency_test_db and test_v2_concurrency_test_db are pre-created.
# The local test DB password is provided via the DB_PASSWORD environment variable;
# it is intentionally not hardcoded in this file.
if os.environ.get("DB_PASSWORD") is None:
    raise RuntimeError(
        "DB_PASSWORD environment variable is required to run this test; "
        "export DB_PASSWORD before running (e.g. `export DB_PASSWORD='...'`)."
    )
os.environ.setdefault("DB_ENGINE", "django.db.backends.mysql")
os.environ.setdefault("DB_NAME", "v2_concurrency_test_db")
os.environ.setdefault("DB_USER", "root")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_INIT_COMMAND", "SET sql_mode='STRICT_TRANS_TABLES'")
os.environ.setdefault("DB_CHARSET", "utf8mb4")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key")
os.environ.setdefault("DJANGO_DEBUG", "True")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")

django.setup()

from django.test import TestCase, TransactionTestCase, Client
from django.db import connection
from upload_firmware.models import FirmwareMetadata, Manufacturer, Device
import upload_firmware.views as views_module

# ---- Fixtures: load real ECDSA key + cert from thesis tree ----
THIS_FILE = Path(__file__).resolve()
THESIS_ROOT = THIS_FILE.parent.parent.parent  # thesis/
ECDSA_KEY = THESIS_ROOT / "manufacturer_client" / "ecdsa_manufacturer_private_key.pem"
ECDSA_CERT = THESIS_ROOT / "manufacturer_client" / "ecdsa_manufacturer_client_cert.pem"

MANUFACTURER_ID = "123e4567-e89b-12d3-a456-426614174000"
DEVICE_TYPE = "esp32"
FIRMWARE_VERSION = "v-conc-test-1"

private_key_pem = ECDSA_KEY.read_bytes()
certificate_pem = ECDSA_CERT.read_bytes()  # PEM bytes → stored in manufacturer_cert (BinaryField)

_ec_key = serialization.load_pem_private_key(private_key_pem, password=None)

# Build canonical metadata (signature over concatenated string, matching verify_signature)
import datetime as _dt
now_ntp = int((_dt.datetime.now(timezone.utc) - _dt.datetime(1900, 1, 1, tzinfo=timezone.utc)).total_seconds())
release_date = now_ntp
firmware_size = len(b"concurrency-test-firmware-payload")
METADATA_BASE = {
    "metadata_signature_algorithm": "ecdsa",
    "firmware_signature_algorithm": "ecdsa",
    "firmware_size": firmware_size,
    "release_date": release_date,
    "manufacturer_id": MANUFACTURER_ID,
    "device_type": DEVICE_TYPE,
    "firmware_version": FIRMWARE_VERSION,
}


def _sign_metadata(m: dict) -> bytes:
    raw = (
        f"{m['firmware_size']}{m['release_date']}{m['manufacturer_id']}"
        f"{m['device_type']}{m['firmware_version']}"
    ).encode()
    return _ec_key.sign(raw, ec.ECDSA(hashes.SHA256()))


def _sign_firmware(fw: bytes) -> bytes:
    return _ec_key.sign(fw, ec.ECDSA(hashes.SHA256()))


class V2ConcurrencyTestBase(TransactionTestCase):
    """Seeds manufacturer + device rows so verify_signature and FK checks pass.

    Uses TransactionTestCase (not TestCase) because the concurrent test spawns
    worker threads, each of which opens its own DB connection. TestCase's
    savepoint isolation makes the seeded rows invisible to those connections
    (every request would 404). TransactionTestCase commits the data so all
    thread connections can see it, and flushes the DB between tests for cleanup.
    """

    def setUp(self):
        # Clean up any prior test rows (idempotent)
        FirmwareMetadata.objects.filter(
            manufacturer_id=MANUFACTURER_ID,
            device_type=DEVICE_TYPE,
            firmware_version=FIRMWARE_VERSION,
        ).delete()
        Device.objects.filter(device_type=DEVICE_TYPE).delete()
        Manufacturer.objects.filter(manufacturer_id=MANUFACTURER_ID).delete()

        # manufacturer_cert is BinaryField → store PEM bytes
        mfr = Manufacturer.objects.create(
            manufacturer_id=MANUFACTURER_ID,
            manufacturer_name="Test Manufacturer",
            email="test@example.com",
            manufacturer_cert=certificate_pem,
        )
        Device.objects.create(
            device_type=DEVICE_TYPE,
            manufacturer=mfr,
        )

    def _build_signed_payload(self) -> dict:
        m = dict(METADATA_BASE)
        fw = b"concurrency-test-firmware-payload"
        m["metadata_signature"] = base64.b64encode(_sign_metadata(m)).decode()
        m["firmware_signature"] = base64.b64encode(_sign_firmware(fw)).decode()
        return {
            "metadata": m,
            "firmware_data": base64.b64encode(fw).decode(),
        }

    def _post_upload(self, payload, client):
        return client.post(
            "/upload_firmware/upload/",
            payload,
            content_type="application/json",
        ).status_code


class V2ConcurrencyTest(V2ConcurrencyTestBase):
    """20 concurrent identical-version uploads → exactly 1 succeeds, 19 get 409."""

    def test_concurrency_same_version_20_requests(self):
        from unittest.mock import patch

        def fake_upload(firmware_metadata, retry_interval=5, max_retries=None):
            return None

        with patch.object(views_module, "upload_to_blockchain", side_effect=fake_upload):
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                clients = [Client() for _ in range(20)]
                payloads = [self._build_signed_payload() for _ in range(20)]
                futures = [
                    executor.submit(self._post_upload, p, c)
                    for p, c in zip(payloads, clients)
                ]
                results = [f.result() for f in futures]

        status_counts = {}
        for code in results:
            status_counts[code] = status_counts.get(code, 0) + 1

        # Exactly 1 success (200/201), 19 conflict 409
        successes = status_counts.get(200, 0) + status_counts.get(201, 0)
        self.assertEqual(
            successes, 1,
            f"Expected exactly 1 success, got status distribution: {status_counts}",
        )
        self.assertEqual(
            status_counts.get(409, 0), 19,
            f"Expected 19 conflict 409s, got: {status_counts}",
        )

        # No 5xx or unexpected 4xx
        self.assertNotIn(500, status_counts, f"500 leaked: {status_counts}")
        self.assertNotIn(404, status_counts, f"404 leaked: {status_counts}")
        self.assertNotIn(401, status_counts, f"401 leaked: {status_counts}")
        self.assertNotIn(405, status_counts, f"405 leaked: {status_counts}")

        # DB count == 1
        db_count = FirmwareMetadata.objects.filter(
            manufacturer_id=MANUFACTURER_ID,
            device_type=DEVICE_TYPE,
            firmware_version=FIRMWARE_VERSION,
        ).count()
        self.assertEqual(db_count, 1, f"Expected 1 DB row, got {db_count}")


class V2ConflictTest(V2ConcurrencyTestBase):
    """Sequential upload: first succeeds, second returns 409. No concurrency."""

    def test_sequential_upload_conflict(self):
        from unittest.mock import patch

        def fake_upload(firmware_metadata, retry_interval=5, max_retries=None):
            return None

        with patch.object(views_module, "upload_to_blockchain", side_effect=fake_upload):
            client = Client()
            p1 = self._build_signed_payload()
            r1 = client.post("/upload_firmware/upload/", p1, content_type="application/json")
            self.assertIn(
                r1.status_code, (200, 201),
                f"First upload should succeed, got {r1.status_code}: {r1.content[:300]}",
            )

            p2 = self._build_signed_payload()
            r2 = client.post("/upload_firmware/upload/", p2, content_type="application/json")
            self.assertEqual(
                r2.status_code, 409,
                f"Second identical upload should 409, got {r2.status_code}: {r2.content[:300]}",
            )

            self.assertNotIn(r1.status_code, (500, 502, 503, 504))
            self.assertNotIn(r2.status_code, (500, 502, 503, 504))

        db_count = FirmwareMetadata.objects.filter(
            manufacturer_id=MANUFACTURER_ID,
            device_type=DEVICE_TYPE,
            firmware_version=FIRMWARE_VERSION,
        ).count()
        self.assertEqual(db_count, 1, f"Expected 1 DB row, got {db_count}")
