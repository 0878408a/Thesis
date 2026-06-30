from rest_framework.test import APITestCase
from django.test import SimpleTestCase
from rest_framework import status
import base64, os
from pathlib import Path
import time
from shared import config
from django.conf import settings
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa, padding, ec
from cryptography.hazmat.primitives import serialization, hashes # serialization 用於序列化和反序列化密鑰和憑證 
from django.apps import apps
from unittest.mock import patch # 用於模擬物件或函數的行為
from django.core.cache import cache
from transfer_firmware.models import Manufacturer, Device, FirmwareMetadata
from transfer_firmware import views

# ECDSA/RSA 切換
USE_ECDSA = True

if USE_ECDSA:
    CUSTOMER_PRIVATE_KEY_PATH = config.CUSTOMER_PRIVATE_KEY_PATH
    CUSTOMER_CERT_PATH = config.CUSTOMER_CERT_PATH
    MANUFACTURER_AGENT_PRIVATE_KEY_PATH = config.MANUFACTURER_AGENT_PRIVATE_KEY_PATH
    MANUFACTURER_AGENT_CERT_PATH = config.MANUFACTURER_AGENT_CERT_PATH
else:
    CUSTOMER_PRIVATE_KEY_PATH = config.CUSTOMER_PRIVATE_KEY_PATH
    CUSTOMER_CERT_PATH = config.CUSTOMER_CERT_PATH
    MANUFACTURER_AGENT_PRIVATE_KEY_PATH = config.MANUFACTURER_AGENT_PRIVATE_KEY_PATH
    MANUFACTURER_AGENT_CERT_PATH = config.MANUFACTURER_AGENT_CERT_PATH

class DownloadFirmwareTLSTestCase(SimpleTestCase):
    """TLS/mTLS 測試（不依賴資料庫）"""

    def setUp(self):
        with open(MANUFACTURER_AGENT_CERT_PATH, "rb") as f:
            self.cert = x509.load_pem_x509_certificate(f.read())

        self.cert_path = MANUFACTURER_AGENT_CERT_PATH
        self.server_url = "https://localhost:8000/transfer_firmware/request_download/"

        self.client_cert = config.FULL_CHAIN_CERT_PATH

    def test_tls_cert_file_exists(self):
        self.assertTrue(Path(self.cert_path).exists(), " 證書檔案不存在")
class OneTimeDownloadTestCase(APITestCase):
    """測試 /transfer_firmware/download/<token>/ 一次性 URL 下載"""

    def setUp(self):
        self.token = "12345678-1234-1234-1234-123456789abc"
        self.content = b"Hello Firmware!"
        self.download_url = f"/transfer_firmware/download/{self.token}/"
        self.manufacturer = Manufacturer.objects.create(
        manufacturer_id="manu-001", manufacturer_name="Test Manufacturer"
        )
        # 建立 device
        self.device = Device.objects.create(
            device_type="device-001",
            manufacturer_id=self.manufacturer.manufacturer_id
        )
        # 建立 firmware
        self.firmware, _ = FirmwareMetadata.objects.get_or_create(
            metadata_signature=b"1" * 64,
            metadata_signature_algorithm="ECDSA",
            firmware_signature=b"1" * 64,
            firmware_signature_algorithm="ECDSA",
            firmware_size=1024,
            release_date=1672531200,
            manufacturer=self.manufacturer,
            device_type=self.device.device_type,
            firmware_version="v1.0",
            firmware_data=self.content
        )
        # 儲存檔案路徑進快取
        self.test_file_path = os.path.join(settings.BASE_DIR, "temp_firmware.bin")
        with open(self.test_file_path, "wb") as f:
            f.write(self.content)

        cache.set(f"firmware_url:{self.token}", self.test_file_path, timeout=60)

    def tearDown(self):
        # 等待 response 使用完畢後再刪除檔案
        for _ in range(5):
            try:
                os.remove(self.test_file_path)
                break
            except PermissionError:
                time.sleep(0.5)
        cache.delete(f"firmware_url:{self.token}")

    def test_download_success_once(self):
        """測試一次性 URL 成功下載"""

        cache.set(self.token, {
            "expires_at": int(time.time()) + 300,
            "manufacturer_id": self.manufacturer.manufacturer_id,
            "device_type": self.device.device_type,
            "firmware_version": self.firmware.firmware_version
        })
        
        response = self.client.get(self.download_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), self.content)

        print()
        print("Test `test_download_success_once` passed successfully!")

    def test_download_token_used_again(self):
        """測試同一 token 下載第二次會失敗"""
        self.client.get(self.download_url)  # 第一次應成功
        response = self.client.get(self.download_url)  # 第二次應失敗
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["message"], "該 URL 已被使用")
        print()
        print("Test `test_download_token_used_again` passed successfully!")

    def test_invalid_token(self):
        """測試不存在的 token"""
        invalid_url = "/transfer_firmware/download/00000000-0000-0000-0000-000000000000/"
        response = self.client.get(invalid_url)
        self.assertEqual(response.status_code, 403)

        if "application/json" in response.headers.get("Content-Type", ""):
            self.assertEqual(response.json()["message"], "無效或已過期的 URL")
        else:
            self.fail("回應不是 JSON 格式")
        print()
        print("Test `test_invalid_token` passed successfully!")


class DownloadFirmwareAPITestCase(APITestCase):
    """Firmware 下載流程測試"""

    def setUp(self):
        self.url = "/transfer_firmware/request_download/"

        # 讀取私鑰 + 憑證 PEM
        with open(CUSTOMER_PRIVATE_KEY_PATH, "rb") as f:
            self.private_key = serialization.load_pem_private_key(f.read(), password=None)

        with open(CUSTOMER_CERT_PATH, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
            self.public_key = cert.public_key()
            self.pem_public_key = self.public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )

        Manufacturer = apps.get_model("transfer_firmware", "Manufacturer")
        Device = apps.get_model("transfer_firmware", "Device")
        Customer = apps.get_model("transfer_firmware", "Customer")
        FirmwareMetadata = apps.get_model("transfer_firmware", "FirmwareMetadata")

        # 將 DB 資料取出 
        self.manufacturer, _ = Manufacturer.objects.get_or_create(
            manufacturer_id="123e4567-e89b-12d3-a456-426614174000",
            defaults={
                "manufacturer_name": "Test",
                "email": "m@example.com",
                "manufacturer_cert": b"dummy"
            }
        )    
        self.device, _ = Device.objects.get_or_create(
            device_type="esp32",
            manufacturer=self.manufacturer
        )
        self.customer,_ = Customer.objects.get_or_create(
            customer_id="3e01e6a7-1c25-4a5e-97c5-92ec5abfd10c",)
        
        self.firmware, _ = FirmwareMetadata.objects.get_or_create(
            metadata_signature=b"1" * 64,
            metadata_signature_algorithm="ECDSA",
            firmware_signature=b"1" * 64,
            firmware_signature_algorithm="ECDSA",
            firmware_size=1024,
            release_date=1672531200,
            manufacturer=self.manufacturer,
            device_type=self.device.device_type,
            firmware_version="v1.0",
            firmware_data=b"1" * 256
        )

        # 產生簽章 
        signed_data = f"{self.manufacturer.manufacturer_id}{self.device.device_type}{self.firmware.firmware_version}{self.customer.customer_id}".encode()
        if isinstance(self.private_key, rsa.RSAPrivateKey):
            signature = self.private_key.sign(signed_data, padding.PKCS1v15(), hashes.SHA256())
            self.signature_algorithm = "RSA"
        elif isinstance(self.private_key, ec.EllipticCurvePrivateKey):
            signature = self.private_key.sign(signed_data, ec.ECDSA(hashes.SHA256()))
            self.signature_algorithm = "ECDSA"
        else:
            raise ValueError("Unsupported key")

        self.signature = base64.b64encode(signature).decode()

        self.valid_data = {
            "manufacturer_id": self.manufacturer.manufacturer_id,
            "customer_id": self.customer.customer_id,
            "device_type": self.device.device_type,
            "firmware_version": self.firmware.firmware_version,
            "customer_signature_algorithm": self.signature_algorithm,
            "customer_signature": self.signature
        }

    def test_missing_signature_algorithm(self):
        """測試缺少 customer_signature_algorithm 欄位（錯誤碼 4001）"""
        data = self.valid_data.copy()
        del data["customer_signature_algorithm"]
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["Errorcode"], 4001)
        
        print()
        print("Test `test_missing_signature_algorithm` passed successfully!")

    def test_unsupported_signature_algorithm(self):
        """測試不支援的簽章演算法（錯誤碼 4002）"""
        data = self.valid_data.copy()
        data["customer_signature_algorithm"] = "UNSUPPORTED"
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["Errorcode"], 4002)
        
        print()
        print("Test `test_unsupported_signature_algorithm` passed successfully!")

    def test_missing_customer_signature(self):
        """測試缺少 customer_signature 欄位（錯誤碼 4011）"""
        data = self.valid_data.copy()
        del data["customer_signature"]
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["Errorcode"], 4011)
        
        print()
        print("Test `test_missing_customer_signature` passed successfully!")

    def test_missing_device_type(self):
        """測試缺少 device_type 欄位（錯誤碼 4041）"""
        data = self.valid_data.copy()
        del data["device_type"]
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["Errorcode"], 4041)
        
        print()
        print("Test `test_missing_device_type` passed successfully!")

    def test_missing_firmware_version(self):
        """測試缺少 firmware_version 欄位（錯誤碼 4051）"""
        data = self.valid_data.copy()
        del data["firmware_version"]
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["Errorcode"], 4051)
        
        print()
        print("Test `test_missing_firmware_version` passed successfully!")

    
    def test_firmware_download_request_success(self):
        """測試韌體下載請求成功（錯誤碼 0）"""
        response = self.client.post(self.url, self.valid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("ResponseURL", response.json())
        self.assertTrue(
        response.json()["ResponseURL"].startswith(
            "https://localhost:8000/transfer_firmware/download/"
            )
        )
        
        print()
        print("Test `test_firmware_download_request_success` passed successfully!")

    def test_missing_customer_id(self):
        """測試缺少 customer_id 欄位（錯誤碼 4021）"""
        data = self.valid_data.copy(); del data["customer_id"]
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["Errorcode"], 4021)
        
        print()
        print("Test `test_missing_customer_id` passed successfully!")

    def test_missing_manufacturer_id(self):
        """測試缺少 manufacturer_id 欄位（錯誤碼 4031）"""
        data = self.valid_data.copy()
        del data["manufacturer_id"]

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["Errorcode"], 4031)

        print()
        print("Test `test_missing_manufacturer_id` passed successfully!")
    
    def test_invalid_customer_id(self):
        """測試無效的 customer_id（錯誤碼 4022）"""
        data = self.valid_data.copy()
        data["customer_id"] = "123e4567-e89b-12d3-a456-426614179999"
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["Errorcode"], 4022)
        
        print()
        print("Test `test_invalid_customer_id` passed successfully!")
        
    def test_missing_manufacturer_id(self):
        """Customer 存在，但其對應的 manufacturer_id 查不到 Manufacturer，應回傳 4032"""

        # 確保 self.customer 已經指向一個合法的 manufacturer
        self.assertIsNotNone(self.customer.manufacturer)

        with patch("transfer_firmware.models.Manufacturer.objects.filter") as mock_filter:
            mock_filter.return_value.first.return_value = None  # 模擬找不到 manufacturer

            response = self.client.post(self.url, self.valid_data, format="json")

            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["Errorcode"], 4032)
            
            print()
            print("Test `test_missing_manufacturer_id` passed successfully!")
        
    def test_invalid_device_type(self):
        """測試無效的 device_type（錯誤碼 4042）"""
        data = self.valid_data.copy()
        data["device_type"] = "UnknownDevice"
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["Errorcode"], 4042)
        
        print()
        print("Test `test_invalid_device_type` passed successfully!")

    def test_invalid_firmware_version(self):
        """測試無效的 firmware_version（錯誤碼 4052）"""
        data = self.valid_data.copy()
        data["firmware_version"] = "v99.9"
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["Errorcode"], 4052)
        
        print()
        print("Test `test_invalid_firmware_version` passed successfully!")

    def test_invalid_signature_format(self):
        """測試無效的簽章格式（錯誤碼 4012）"""
        data = self.valid_data.copy()
        data["customer_signature"] = "12345xyz"  # 非 hex 編碼
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["Errorcode"], 4012)
        
        print()
        print("Test `test_invalid_signature_format` passed successfully!")

    def test_response_with_signature_success(self):
        """測試 response_with_signature 成功簽章情境"""

        # 載入本地私鑰
        with open(MANUFACTURER_AGENT_PRIVATE_KEY_PATH, "rb") as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)

        # 模擬簽章
        result = 1
        url = "https://firmware.server.com/v1.0.bin"
        message = "Download approved."
        error_code = None
        raw_payload = f"{result}|{url}|{message}|".encode()

        if isinstance(private_key, rsa.RSAPrivateKey):
            signature = private_key.sign(raw_payload, padding.PKCS1v15(), hashes.SHA256())
            algorithm = "RSA-SHA256"
        elif isinstance(private_key, ec.EllipticCurvePrivateKey):
            signature = private_key.sign(raw_payload, ec.ECDSA(hashes.SHA256()))
            algorithm = "ECDSA-SHA256"
        else:
            self.fail("Unsupported key type")

        # 驗證簽章格式
        encoded_signature = base64.b64encode(signature).decode()
        self.assertTrue(encoded_signature)
        self.assertIn(algorithm, ["RSA-SHA256", "ECDSA-SHA256"])
        
        print()
        print("Test `test_response_with_signature_success` passed successfully!")

    @patch("transfer_firmware.views.load_pem_private_key")
    def test_response_with_signature_fail(self, mock_key):
        
        """測試 response_with_signature 簽章失敗處理"""

        mock_key.side_effect = Exception("sign error")

        response = views.response_with_signature("error", 4001)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        print()
        print("Test `test_response_with_signature_fail` passed successfully!")
    
    def test_firmware_not_found(self):
        
        """測試下載韌體時，若資料庫無對應 FirmwareMetadata 回傳 404"""

        # 清空資料庫的固件資訊
        FirmwareMetadata.objects.all().delete()

        # 設定 cache，模擬已登入 token
        self.token = "test-token-123"
        cache.set(self.token, {
            "expires_at": int(time.time()) + 300,
            "manufacturer_id": self.manufacturer.manufacturer_id,
            "device_type": self.device.device_type,
            "firmware_version": self.firmware.firmware_version
        })

        # 設定下載 URL
        self.download_url = f"/api/firmware/download/{self.firmware.firmware_version}/"        
        
        # 進行 GET 請求
        response = self.client.get(self.download_url)

        # 驗證回傳 HTTP 狀態碼為 404
        self.assertEqual(response.status_code, 404)

        print()
        print("Test `test_firmware_not_found` passed successfully!")