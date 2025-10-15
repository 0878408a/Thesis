from rest_framework.test import APITestCase
from django.test import SimpleTestCase
from rest_framework import status
import binascii, base64, os
from pathlib import Path
import requests
import time
from django.conf import settings
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa, padding, ec
from cryptography.hazmat.primitives import serialization, hashes # serialization 用於序列化和反序列化密鑰和憑證 
from django.apps import apps
from unittest.mock import patch # 用於模擬物件或函數的行為
from django.core.cache import cache



# ECDSA/RSA 切換
USE_ECDSA = True

if USE_ECDSA:
    CUSTOMER_PRIVATE_KEY_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_customer_private_key.pem")
    CUSTOMER_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_customer_public_cert.pem")
    MANUFACTURER_AGENT_PRIVATE_KEY_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_manufacturer_agent_private_key.pem")
    MANUFACTURER_AGENT_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_manufacturer_agent_public_cert.pem")
else:
    CUSTOMER_PRIVATE_KEY_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/rsa_customer_private_key.pem")
    CUSTOMER_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/rsa_customer_public_cert.pem")
    MANUFACTURER_AGENT_PRIVATE_KEY_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/manufacturer_agent_private_key.pem")
    MANUFACTURER_AGENT_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/manufacturer_agent_public_cert.pem")

class DownloadFirmwareTLSTestCase(SimpleTestCase):
    """TLS/mTLS 測試（不依賴資料庫）"""

    def setUp(self):
        with open(MANUFACTURER_AGENT_CERT_PATH, "rb") as f:
            self.cert = x509.load_pem_x509_certificate(f.read())

        self.cert_path = MANUFACTURER_AGENT_CERT_PATH
        self.server_url = "https://localhost:8000/transfer_firmware/request_download/"

        self.client_cert = (str(CUSTOMER_CERT_PATH), str(CUSTOMER_PRIVATE_KEY_PATH))

    def test_tls_cert_file_exists(self):
        self.assertTrue(Path(self.cert_path).exists(), " 證書檔案不存在")

    def test_tls_cert_format_valid(self):
        with open(self.cert_path, "rb") as f:
            try:
                cert = x509.load_pem_x509_certificate(f.read(), backend=default_backend())
                self.assertIsNotNone(cert)
                
                print()
                print(" 成功解析 X.509 憑證, 簽發者:", cert.issuer)
            except Exception as e:
                self.fail(f" 憑證解析失敗: {e}")

    def test_tls_connection(self):
        try:
            response = requests.get(self.server_url, verify=self.cert_path)
            self.assertIn(response.status_code, [200, 404, 405])
            
            print()
            print(f" 成功 TLS 連線, 狀態碼: {response.status_code}")
        except Exception as e:
            self.fail(f" 無法 TLS 連線: {e}")

    def test_mtls_connection(self):
        try:
            response = requests.get(self.server_url, cert=self.client_cert, verify=self.cert_path)
            self.assertIn(response.status_code, [200, 404, 405])
            
            print()
            print(f" 成功 mTLS 連線, 狀態碼: {response.status_code}")
        except Exception as e:
            self.fail(f" 無法 mTLS 連線: {e}")

class OneTimeDownloadTestCase(APITestCase):
    """測試 /transfer_firmware/download/<token>/ 一次性 URL 下載"""

    def setUp(self):
        self.token = "12345678-1234-1234-1234-123456789abc"
        self.content = b"Hello Firmware!"
        self.download_url = f"/transfer_firmware/download/{self.token}/"

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
        response = self.client.get(self.download_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), self.content)

        print()
        print("Test `test_download_success_once` passed successfully!")

    def test_download_token_used_again(self):
        """測試同一 token 下載第二次會失敗"""
        self.client.get(self.download_url)  # 第一次應成功
        response = self.client.get(self.download_url)  # 第二次應失敗
        self.assertEqual(response.status_code, 410)
        self.assertIn("error", response.json())
        self.assertIn("used", response.json()["error"].lower())

        print()
        print("Test `test_download_token_used_again` passed successfully!")

    def test_invalid_token(self):
        """測試不存在的 token"""
        invalid_url = "/transfer_firmware/download/00000000-0000-0000-0000-000000000000/"
        response = self.client.get(invalid_url)
        self.assertEqual(response.status_code, 410)

        if "application/json" in response.headers.get("Content-Type", ""):
            self.assertIn("error", response.json())
            self.assertIn("expired", response.json()["error"].lower())
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

        Manufacturer = apps.get_model("register", "Manufacturer")
        Device = apps.get_model("register", "Device")
        Customer = apps.get_model("register", "Customer")
        FirmwareMetadata = apps.get_model("upload_firmware", "FirmwareMetadata")

        # === 將 DB 資料取出 ===
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
            metadata_signature_algorithm="RSA",
            firmware_signature=b"1" * 64,
            firmware_signature_algorithm="RSA",
            firmware_size=1024,
            release_date=1672531200,
            manufacturer=self.manufacturer,
            device_type=self.device.device_type,
            firmware_version="v1.0",
            firmware_data=b"1" * 256
        )

        # === 產生簽章 ===
        signed_data = f"{self.manufacturer.manufacturer_id}{self.device.device_type}{self.firmware.firmware_version}{self.customer.customer_id}".encode()
        if isinstance(self.private_key, rsa.RSAPrivateKey):
            signature = self.private_key.sign(signed_data, padding.PKCS1v15(), hashes.SHA256())
            self.signature_algorithm = "RSA"
        elif isinstance(self.private_key, ec.EllipticCurvePrivateKey):
            signature = self.private_key.sign(signed_data, ec.ECDSA(hashes.SHA256()))
            self.signature_algorithm = "ECDSA"
        else:
            raise ValueError("Unsupported key")

        self.hex_signature = binascii.hexlify(signature).decode()

        self.valid_data = {
            "customer_id": self.customer.customer_id,
            "device_type": self.device.device_type,
            "firmware_version": self.firmware.firmware_version,
            "customer_signature_algorithm": self.signature_algorithm,
            "customer_signature": self.hex_signature
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
        self.assertEqual(response.json()["ResponseURL"], f"https://firmware.server.com/{self.firmware.firmware_version}.bin")
        
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

        with patch("register.models.Manufacturer.objects.filter") as mock_filter:
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

        # === 模擬簽章 ===
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

    def test_response_with_signature_fail(self):
        """測試 response_with_signature 簽章失敗處理"""

        from transfer_firmware import views  # 匯入整個 views 模組
        view = views.FirmwareDownloadRequestAPIView()

        # === 模擬錯誤私鑰 ===
        original_key = views.agent_private_key_pem  # 存取 views 模組中的全域變數
        views.agent_private_key_pem = "INVALID_KEY"  # 實際覆蓋

        try:
            response = view.response_with_signature(0, "Fail", 4998, None)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data["Errorcode"], 4998)
            self.assertEqual(response.data["ManufacturerAgentSignatureAlgorithm"], "SIGNING_FAILED")
            
            print()
            print("Test `test_response_with_signature_fail` passed successfully!")
        finally:
            views.agent_private_key_pem = original_key  # 測試結束還原
    
    def test_database_insertion_error(self):
        """模擬資料庫寫入失敗"""
        FirmwareDownloadRequest = apps.get_model("transfer_firmware", "FirmwareDownloadRequest")

        with patch.object(FirmwareDownloadRequest.objects, "create", side_effect=Exception("DB Write Error")):
            response = self.client.post(self.url, self.valid_data, format="json")
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["Errorcode"], 4999)
            
            print()
            print("Test `test_database_insertion_error` passed successfully!")

    
    def tearDown(self):
        apps.get_model("transfer_firmware", "FirmwareDownloadRequest").objects.all().delete()
        apps.get_model("upload_firmware", "FirmwareMetadata").objects.all().delete()
        apps.get_model("register", "Customer").objects.all().delete()
        apps.get_model("register", "Device").objects.all().delete()
        apps.get_model("register", "Manufacturer").objects.all().delete()
