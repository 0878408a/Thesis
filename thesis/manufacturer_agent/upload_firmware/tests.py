import os
from rest_framework.test import APITestCase
from rest_framework import status
from shared import config
import base64
import copy 
import datetime
import uuid
from django.apps import apps # 用於動態載入 Django 應用程式的模型
from django.db.utils import IntegrityError # 這個模組提供了與資料庫相關的錯誤處理
from unittest.mock import patch # 用於模擬外部 API 回傳錯誤
from cryptography.hazmat.primitives.asymmetric import rsa, ec, padding
from cryptography.hazmat.primitives import serialization, hashes
# serialization 用於將金鑰轉換為 PEM 格式
from cryptography import x509 
from cryptography.hazmat.backends import default_backend 
# default_backend() 是一個函數，用於獲取當前可用的加密後端
from pathlib import Path
from unittest.mock import patch
from django.test import SimpleTestCase # SimpleTestCase 才支援測試 TLS/mTLS


"""事前宣告私鑰及憑證路徑"""

USE_ECDSA = True  # 改成 False 即可改用 RSA 簽章測試

if USE_ECDSA:
    
    # 使用 NIST P-256 標準生成，金鑰長度 256 bits，強度等於 RSA 3072 bits
    MANUFACTURER_PRIVATE_KEY_PATH = config.MANUFACTURER_PRIVATE_KEY_PATH
    MANUFACTURER_CERT_PATH = config.MANUFACTURER_CERT_PATH
    MANUFACTURER_AGENT_PRIVATE_KEY_PATH = config.MANUFACTURER_AGENT_PRIVATE_KEY_PATH
    MANUFACTURER_AGENT_CERT_PATH = config.MANUFACTURER_AGENT_CERT_PATH

else:
    
    # 使用 RSA 4096 bits 生成
    MANUFACTURER_PRIVATE_KEY_PATH = config.MANUFACTURER_PRIVATE_KEY_PATH
    MANUFACTURER_CERT_PATH = config.MANUFACTURER_CERT_PATH
    MANUFACTURER_AGENT_PRIVATE_KEY_PATH = config.MANUFACTURER_AGENT_PRIVATE_KEY_PATH
    MANUFACTURER_AGENT_CERT_PATH = config.MANUFACTURER_AGENT_CERT_PATH

class UploadFirmwareTLSTestCase(SimpleTestCase):
    
    """TLS 憑證測試用例）"""

    def setUp(self):
        
        with open(MANUFACTURER_AGENT_CERT_PATH, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        
        self.cert_path = MANUFACTURER_AGENT_CERT_PATH
        self.server_url = "https://localhost:8000/upload_firmware/upload/"         
        self.client_cert = (
           
            str(MANUFACTURER_CERT_PATH),         # manufacturer 憑證
            str(MANUFACTURER_PRIVATE_KEY_PATH)   # manufacturer 私鑰
        
        )
        
    def test_tls_cert_file_exists(self):
        
        """確認自簽憑證檔案存在"""
        
        # assertTrue() 是 Python 的 unittest 測試框架中常用的 assert 方法，用來確認一個條件是否為 True。
        self.assertTrue(Path(self.cert_path).exists(), " 憑證檔案不存在！")

    def test_tls_cert_format_valid(self):
        
        """測試憑證為有效的 X.509 格式"""
       
        with open(self.cert_path, "rb") as f:
            
            try:
                
                cert = x509.load_pem_x509_certificate(f.read(), backend=default_backend())
                
                # assertIsNotNone() 是 Python 的 unittest 測試框架中常用的 assert 方法，用來確認一個物件是否為 None。
                self.assertIsNotNone(cert)
                print() 
                print(" 成功解析 X.509 憑證，簽發者：", cert.issuer)
            
            except Exception as e:
                
                self.fail(f" 憑證解析失敗: {e}")

class UploadFirmwareAPITestCase(APITestCase):
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # patch upload_to_blockchain
        cls.patcher = patch("upload_firmware.views.upload_to_blockchain")
        cls.mock_upload = cls.patcher.start()
        cls.mock_upload.return_value = None  # 模擬上鏈成功

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()
        super().tearDownClass()
    
    """測試上傳韌體 API"""
    
    # setUp() 是 Django 測試框架 (unittest TestCase) 的方法，在每個測試方法 (test_xxx) 執行前自動執行，用來初始化測試數據。
    
    def setUp(self):
        
        """初始化測試數據"""
        self.url = "/upload_firmware/upload/" #

        # 讀取 manufacturer 私鑰（來自本機產生的檔案）
        with open(MANUFACTURER_PRIVATE_KEY_PATH, "rb") as f:
            self.private_key = serialization.load_pem_private_key(f.read(), password=None)
        
        # 將私鑰轉成 PEM 字串格式，以便將私鑰傳給測試韌體簽章後上傳 API（363行）
        self.pem_private_key_str = self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ).decode()
        
        # 取得 models
        # apps.get_model() 是 Django 的 django.apps 模組提供的方法，
        # 用來在執行期間 (runtime) 動態載入 (import) 指定應用程式 (app) 下的模型 (model)。
        
        Manufacturer = apps.get_model('upload_firmware', 'Manufacturer')
        Device = apps.get_model('upload_firmware', 'Device')
        
        '''
            先將資料庫內的 Manufacturer 資料取出來，
            get_or_create() 是 Django ORM 提供的方法
            主要用於：如果資料庫中已經存在符合條件的物件，則直接獲取它；如果物件不存在，則創建並回傳該物件
        
            get_or_create() 運作邏輯如下：
        
                用前面的參數當成查詢條件去 SELECT（這些通常是 unique 的）

                如果有找到，就直接回傳資料 + created=False

                如果找不到，就用這些條件 + defaults 合併來 INSERT
        '''
        with open(MANUFACTURER_CERT_PATH, "rb") as f:
            manufacturer_cert_bytes = f.read()
            
        self.manufacturer_id = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
        self.manufacturer, created = Manufacturer.objects.get_or_create(
            manufacturer_id=self.manufacturer_id,
            defaults={
                "manufacturer_name": "AAA",
                "email": "aaa@test.com",
                "manufacturer_cert": manufacturer_cert_bytes,
            }
        )
         
        # 回傳值: created: True 表示是新建立的，False 表示是從資料庫撈出來的
        # print()
        # print(f"[DEBUG] Manufacturer created? {created}")
        
        '''
        
            print()
            print("[DEBUG] 公鑰 PEM:")
            print(self.pem_public_key.decode())
        
        '''
        
        # 將資料庫內的 Device 資料取出來
        
        self.device, _ = Device.objects.get_or_create(
            device_type="esp32")
        
        ''' 
            manufacturer=self.manufacturer,
            defaults={"created_at": datetime.datetime.now()}
            
        '''
        
        # **產生 firmwaremetadata**
        
        # 轉換現在時間為 NTP timestamp
        ntp_now = int((datetime.datetime.now(datetime.timezone.utc) - datetime.datetime(1900,1,1,tzinfo=datetime.timezone.utc)).total_seconds())
        self.ntp_release_date = ntp_now - 1  # 一定比 server 當前時間小

        # 模擬 1024 bytes 的 firmware binary，再轉成 Base64 傳遞格式
        # 使用 len(self.firmware_binary) 讀取 binary 大小，方便更換測試資料

        self.firmware_binary = os.urandom(1024)

        # client 傳送的 firmware_data
        self.correct_firmware_data = base64.b64encode(self.firmware_binary).decode()

        # firmware_size = decode 後的 binary 長度
        self.firmware_size = len(self.firmware_binary)

        self.firmware_version = "test_for_dev"       
        
        # 組合簽章原始資料（raw data，不先雜湊，因為 ECDSA 驗章會自動雜湊）
        # metadata 要簽的資料
        metadata_signed_data = (
            f"{self.firmware_size}"
            f"{self.ntp_release_date}"
            f"{str(self.manufacturer_id)}"
            f"{self.device.device_type}"
            f"{self.firmware_version}"
        ).encode()

        # firmware 要簽的資料 (binary)
        firmware_signed_data = self.firmware_binary

        # 判斷是 RSA 還是 ECDSA，並產生對應簽章與演算法名稱
        # isinstance() 用來檢查一個物件是否是某個特定類型，格式如下：
        # isinstance(變數, 類型)
        if isinstance(self.private_key, rsa.RSAPrivateKey):

            metadata_signature = self.private_key.sign(
                metadata_signed_data,
                padding.PKCS1v15(),
                hashes.SHA256()
            )

            firmware_signature = self.private_key.sign(
                firmware_signed_data,
                padding.PKCS1v15(),
                hashes.SHA256()
            )

            signature_algorithm = "RSA-SHA256"

        elif isinstance(self.private_key, ec.EllipticCurvePrivateKey):

            metadata_signature = self.private_key.sign(
                metadata_signed_data,
                ec.ECDSA(hashes.SHA256())
            )

            firmware_signature = self.private_key.sign(
                firmware_signed_data,
                ec.ECDSA(hashes.SHA256())
            )

            signature_algorithm = "ECDSA-SHA256"

        else:
            raise TypeError("Unsupported private key type")
        
        # 將簽章編碼成 Base64 字串
        base64_metadata_signature = base64.b64encode(metadata_signature).decode()
        base64_firmware_signature = base64.b64encode(firmware_signature).decode()

        self.valid_firmware_data = {
            "firmware_data": self.correct_firmware_data,
            "metadata": {
                "metadata_signature": base64_metadata_signature,
                "metadata_signature_algorithm": signature_algorithm,
                "firmware_signature": base64_firmware_signature,
                "firmware_signature_algorithm": signature_algorithm,
                "firmware_size": self.firmware_size,
                "release_date": self.ntp_release_date,
                "manufacturer_id": str(self.manufacturer_id),
                "device_type": self.device.device_type,
                "firmware_version": self.firmware_version
            }
        }
        
        # print()
        # print("\n[DEBUG] self.valid_firmware_data JSON:")
        # print(json.dumps(self.valid_firmware_data, indent=4))
    
    def test_upload_firmware_success_with_signature(self):
        
        """測試成功上傳韌體並驗證簽章"""
        
        payload = copy.deepcopy(self.valid_firmware_data)
        payload["agent_private_key"] = self.pem_private_key_str

        # 發送 POST 請求
        response = self.client.post(self.url, payload, format="json")
        
        # assertEqual() 是 Python 的 unittest 測試框架中常用的 assert 方法，用來確認兩個值是否相等。
        # 如果兩者相等，測試通過；如果不相等，則測試失敗並顯示錯誤資訊。
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json().get("UploadResult"), 1)
        self.assertEqual(response.json().get("Message"), "Firmware uploaded successfully")
        self.assertEqual(response.json().get("Errorcode"), "")
        
        # 這是一行 Django unittest Assertion 測試 (assertIn())，用來 檢查 API 回應 (response) 是否包含預期的訊息。
        self.assertIn("ManufacturerAgentSignature", response.json())
        expected_algo = "ECDSA-SHA256" if isinstance(self.private_key, ec.EllipticCurvePrivateKey) else "RSA-SHA256"
        self.assertEqual(response.json().get("ManufacturerAgentSignatureAlgorithm"), expected_algo)
        print() 
        print("Test test_upload_firmware_success_with_signature passed successfully!")

    def test_missing_metadata_field(self):
        
        """測試缺少 metadata 欄位"""
        
        required_fields = { 
            "metadata_signature_algorithm": 1001,
            "metadata_signature": 1011,
            "firmware_signature_algorithm": 2001,
            "firmware_signature": 2011,
            "firmware_size": 3001,
            "release_date": 3011,
            "manufacturer_id": 3021,
            "device_type": 3031,
            "firmware_version": 3041,
        }
        
        # 在 Python 中，copy.deepcopy(obj) 會建立 obj 的完全獨立副本，
        # copy.deepcopy(obj) 用於保護原始測試資料 (self.valid_firmware_data) 不被修改，確保其他測試能用到原始資料。
        # 如果沒有使用 copy.deepcopy()，那麼：self.valid_firmware_data 會被直接修改
        # 後續測試的 self.valid_firmware_data 會變成「少了欄位的狀態」，導致測試出錯
        for field, error_code in required_fields.items():
            invalid_data = copy.deepcopy(self.valid_firmware_data)
            invalid_data["metadata"].pop(field)
            response = self.client.post(self.url, invalid_data, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

            # 取得缺失欄位列表
            error_details = response.json().get("Message")
            self.assertTrue(any(d["field"] == field and d["error_code"] == error_code for d in error_details))
                    
            print() 
            print(f"Test test_missing_metadata_field for {field} passed successfully!")
    
    def test_missing_metadata_object(self):

        """測試 metadata 物件缺失（錯誤碼 1000）"""

        invalid_data = copy.deepcopy(self.valid_firmware_data)
        invalid_data.pop("metadata")

        response = self.client.post(self.url, invalid_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("Errorcode"), 1000)

        print()
        print("Test test_missing_metadata_object passed successfully!")
    
    def test_metadata_wrong_type(self):

        """測試 metadata 型別錯誤（錯誤碼 1003）"""

        invalid_data = copy.deepcopy(self.valid_firmware_data)
        invalid_data["metadata"] = "invalid_type"

        response = self.client.post(self.url, invalid_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("Errorcode"), 1003)

        print()
        print("Test test_metadata_wrong_type passed successfully!")
        
    def test_missing_firmware_data(self):
        """測試缺少 firmware_data 欄位（錯誤碼 3051）"""

        invalid_data = copy.deepcopy(self.valid_firmware_data)
        invalid_data.pop("firmware_data")

        response = self.client.post(self.url, invalid_data, format="json")
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("Errorcode"), 3051)

        print()
        print("Test test_missing_firmware_data passed successfully!")

            
    def test_invalid_base64_firmware_data(self):
        
        """測試 firmware_data 不是 base64"""
        
        # self.valid_firmware_data.copy() 
        # 使用.copy() 以便在測試時可以修改其中的數據，而不影響原始的 self.valid_firmware_data
        # 但.copy() 只複製最外層物件，copy.deepcopy()複製所有巢狀結構（遞迴）
        invalid_data = copy.deepcopy(self.valid_firmware_data)
        invalid_data["firmware_data"] = "Invalid@@Base64=="
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("Errorcode"), 3052)
        
        print() 
        print("Test test_invalid_base64_firmware_data passed successfully!")

    def test_invalid_metadata_base64(self):
        
        """測試 metadata_signature 不是 base64"""
        
        invalid_data = copy.deepcopy(self.valid_firmware_data)
        invalid_data["metadata"]["metadata_signature"] = "!!!not_base64$$$"
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("Errorcode"), 1013)
        
        print() 
        print("Test test_invalid_metadata_base64 passed successfully!")

    def test_invalid_firmware_signature_base64(self):
        """測試 firmware_signature 不是 base64（錯誤碼 2013）"""
        
        invalid_data = copy.deepcopy(self.valid_firmware_data)
        invalid_data["metadata"]["firmware_signature"] = "###not_base64@@@"
        
        response = self.client.post(self.url, invalid_data, format="json")
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("Errorcode"), 2013)

        print()
        print("Test test_invalid_firmware_signature_base64 passed successfully!")
    
    def test_firmware_size_mismatch(self):
        
        """測試 firmware_data 長度與 firmware_size 不符"""
        
        invalid_data = copy.deepcopy(self.valid_firmware_data)
        invalid_data["firmware_data"] = base64.b64encode(b"short_data").decode()
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("Errorcode"), 3053)
        
        print()
        print("Test test_firmware_size_mismatch passed successfully!")
        
    def test_metadata_signature_verification_fail(self):
        
        """測試 Metadata 簽章驗證失敗"""
        
        invalid_data = copy.deepcopy(self.valid_firmware_data)
        invalid_data["metadata"]["metadata_signature"] = base64.b64encode(b"wrong_signature").decode()
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("Errorcode"), 1012)
        
        print() 
        print("Test test_metadata_signature_verification_fail passed successfully!")
            
    def test_firmware_signature_verification_fail(self):
        
        """測試 metadata 簽章驗證失敗"""
        
        invalid_data = copy.deepcopy(self.valid_firmware_data)

        # 組合正確的簽章資料
        signed_data = f"{self.firmware_size}{self.ntp_release_date}{self.manufacturer_id}{self.device.device_type}{self.firmware_version}".encode()

        # 修改其中一個欄位（讓簽章失效），但保持格式正確
        tampered_data = signed_data + b"tamper"

        # 根據金鑰類型生成「看似合法但驗證會失敗」的簽章
        
        if isinstance(self.private_key, rsa.RSAPrivateKey):
            invalid_sig = self.private_key.sign(
                tampered_data,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
        elif isinstance(self.private_key, ec.EllipticCurvePrivateKey):
            invalid_sig = self.private_key.sign(
                tampered_data,
                ec.ECDSA(hashes.SHA256())
            )
        else:
            raise TypeError("Unsupported key type")

        # 將 bytes -> base64 字串，模擬一個格式正確但內容錯誤的簽章，然後放進送出的 POST 請求資料中
        # 將 metadata 中的 firmware_signature 欄位替換成錯誤的簽章
        invalid_data["metadata"]["firmware_signature"] = base64.b64encode(invalid_sig).decode()

        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("Errorcode"), 2012)
        
        print() 
        print("Test test_firmware_signature_verification_fail passed successfully!")

            
    # @patch 來自 unittest.mock 模組，它的主要功能是用來模擬（mock）某些物件或函數的行為，
    # Mock = 用假的函式 / 物件，取代真的外部功能，這樣測試時不會真的去呼叫外部系統
    
    @patch("upload_firmware.models.FirmwareMetadata.save")
    def test_database_error(self, mock_save):
        
        """模擬資料庫錯誤，應回傳Errorcode 5001"""
        
        mock_save.side_effect = IntegrityError("Database error")
        response = self.client.post(self.url, self.valid_firmware_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("UploadResult"), 0)
        self.assertEqual(response.json().get("Errorcode"), 5001)
        
        print() 
        print("Test test_database_error passed successfully!")
        
    def test_unsupported_signature_algorithm(self):
        
        """測試 metadata_signature_algorithm 不支援"""
        
        invalid_data = copy.deepcopy(self.valid_firmware_data)
        
        # 將 metadata 中的 firmware_signature 欄位替換成不支援的簽章
        invalid_data["metadata"]["metadata_signature_algorithm"] = "unsupported_algo"
        response = self.client.post(self.url, invalid_data, format="json")
        
        # assertEqual() 是 Python 的 unittest 測試框架中常用的 assert 方法，用來確認兩個值是否相等。
        # 如果兩者相等，測試通過；如果不相等，則測試失敗並顯示錯誤資訊。
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("Errorcode"), 1002)
        
        print()
        print("Test test_unsupported_signature_algorithm passed successfully!")

    def test_unsupported_firmware_signature_algorithm(self):
        
        """測試 firmware_signature_algorithm 不支援"""
        
        invalid_data = copy.deepcopy(self.valid_firmware_data)
        invalid_data["metadata"]["firmware_signature_algorithm"] = "bad_algo"
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("Errorcode"), 2002)
        
        print() 
        print("Test test_unsupported_firmware_signature_algorithm passed successfully!")
        
    def test_nonexistent_manufacturer_id(self):
        
        """測試 manufacturer_id 不存在資料庫中"""
        
        invalid_data = copy.deepcopy(self.valid_firmware_data)
        invalid_data["metadata"]["manufacturer_id"] = str(uuid.uuid4())  # 使用隨機 UUID 模擬不存在的 manufacturer
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.json().get("Errorcode"), 3023)
        print("Test test_nonexistent_manufacturer_id passed successfully!")

    def test_nonexistent_device_type(self):
        
        """測試 device_type 不存在資料庫中"""
        
        invalid_data = copy.deepcopy(self.valid_firmware_data)
        invalid_data["metadata"]["device_type"] = "NonExistentDevice"
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.json().get("Errorcode"), 3032)
        
        print() 
        print("Test test_nonexistent_device_type passed successfully!")

    def post_firmware(self, version):
        
        """
        輔助函式：生成另一個不同版本的 firmware_version 和簽章，
        用於測試不同韌體版本的上傳合法性
        """
        
        payload = copy.deepcopy(self.valid_firmware_data)
        payload["metadata"]["firmware_version"] = version

        # 組合簽章原始資料
        
        signed_data = f"{self.firmware_size}{self.ntp_release_date}{self.manufacturer_id}{self.device.device_type}{version}".encode()

        # 根據金鑰類型進行簽章（RSA 使用 padding，ECDSA 使用 ECDSA(hashes.SHA256())）
        
        if isinstance(self.private_key, rsa.RSAPrivateKey):
            metadata_signature = self.private_key.sign(
                signed_data,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            firmware_signature = self.private_key.sign(
                self.firmware_binary,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
        elif isinstance(self.private_key, ec.EllipticCurvePrivateKey):
            metadata_signature = self.private_key.sign(
                signed_data,
                ec.ECDSA(hashes.SHA256())
            )
            firmware_signature = self.private_key.sign(
                self.firmware_binary,
                ec.ECDSA(hashes.SHA256())
            )
        else:
            raise ValueError("Unsupported private key type")

        # 將簽章編碼為 Base64 字串
        payload["metadata"]["metadata_signature"] = base64.b64encode(metadata_signature).decode()
        payload["metadata"]["firmware_signature"] = base64.b64encode(firmware_signature).decode()

        return self.client.post(self.url, payload, format="json")

    def test_firmware_version_equal_to_existing(self):
        
        """版本相同，應失敗"""
        
        self.post_firmware("test_for_dev")
        response = self.post_firmware("test_for_dev")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("Errorcode"), 3042)

        print() 
        print("Test test_firmware_version_equal_to_existing passed successfully!")
        
    def test_firmware_size_wrong_type(self):
        
        """測試 firmware_size 型別錯誤（錯誤碼 3050）"""
        
        invalid_data = copy.deepcopy(self.valid_firmware_data)
        
        # 將 firmware_size 改成非整數型別（字串）
        invalid_data["metadata"]["firmware_size"] = "not_an_integer"
        
        # 重新生成 metadata_signature，保持資料一致性
        self.regenerate_metadata_signature(invalid_data["metadata"])
        
        # 發送 POST 請求
        response = self.client.post(self.url, invalid_data, format="json")
        
        # 驗證回傳結果
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("Errorcode"), 3050)
        
        print()
        print("Test test_firmware_size_wrong_type passed successfully!")    
    
    def test_invalid_uuid_format(self):
        
        """測試不合法的 UUID 格式"""
        
        invalid_data = copy.deepcopy(self.valid_firmware_data)
        invalid_data["metadata"]["manufacturer_id"] = "not-a-valid-uuid"
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("Errorcode"), 3022)
        
        print() 
        print("Test test_invalid_uuid_format passed successfully!")
    
    def regenerate_metadata_signature(self, metadata):
        '''
        輔助函式：當修改 metadata 中的欄位後，需要重新生成對應的 metadata_signature
        ，才能讓測試資料保持一致性，避免因為簽章驗證失敗
        
        '''
        signed_data = (
            f"{metadata['firmware_size']}"
            f"{metadata['release_date']}"
            f"{metadata['manufacturer_id']}"
            f"{metadata['device_type']}"
            f"{metadata['firmware_version']}"
        ).encode()

        if isinstance(self.private_key, rsa.RSAPrivateKey):
            sig = self.private_key.sign(signed_data, padding.PKCS1v15(), hashes.SHA256())
        elif isinstance(self.private_key, ec.EllipticCurvePrivateKey):
            sig = self.private_key.sign(signed_data, ec.ECDSA(hashes.SHA256()))
        else:
            raise TypeError("Unsupported private key type")

        metadata["metadata_signature"] = base64.b64encode(sig).decode()
    
    def test_negative_ntp_timestamp(self):
        
        """測試 NTP timestamp 為負值"""
        
        # 建立一筆舊版韌體，讓後端走 latest_firmware 分支
        old_data = copy.deepcopy(self.valid_firmware_data)
        old_data["metadata"]["release_date"] = int((datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1) - datetime.datetime(1900,1,1, tzinfo=datetime.timezone.utc)).total_seconds())
        self.regenerate_metadata_signature(old_data["metadata"])
        self.client.post(self.url, old_data, format="json")
        # 測試負值
        invalid_data = copy.deepcopy(self.valid_firmware_data)
        invalid_data["metadata"]["release_date"] = -100
        
        # 重新生成 metadata_signature
        self.regenerate_metadata_signature(invalid_data["metadata"])
        
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("Errorcode"), 3012)
        
        print() 
        print("Test test_negative_ntp_timestamp passed successfully!")

    def test_unreasonably_old_ntp_timestamp(self):
        
        """測試 release_date 為過舊時間（非現在）"""
        
        # 建立一筆舊版韌體
        old_data = copy.deepcopy(self.valid_firmware_data)
        old_data["metadata"]["release_date"] = int((datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1) - datetime.datetime(1900,1,1, tzinfo=datetime.timezone.utc)).total_seconds())
        self.regenerate_metadata_signature(old_data["metadata"])
        self.client.post(self.url, old_data, format="json")
        
        invalid_data = copy.deepcopy(self.valid_firmware_data)
        # 設為 1970-01-01 對應的 NTP timestamp（2208988800）
        invalid_data["metadata"]["release_date"] = 2208988800
        
        # 重新生成 metadata_signature
        self.regenerate_metadata_signature(invalid_data["metadata"])
        
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("Errorcode"), 3012)
        
        print() 
        print("Test test_unreasonably_old_ntp_timestamp passed successfully!")

    def test_unreasonably_future_ntp_timestamp(self):
        
        """測試 release_date 為未來時間（非現在）"""
        
        invalid_data = copy.deepcopy(self.valid_firmware_data)
        # 設為 2101-01-01 的 NTP timestamp（從 1900-01-01 起算秒數）
        future_ntp = int((datetime.datetime(2101, 1, 1, tzinfo=datetime.timezone.utc) - datetime.datetime(1900, 1, 1, tzinfo=datetime.timezone.utc)).total_seconds())
        invalid_data["metadata"]["release_date"] = future_ntp
        
        # 重新生成 metadata_signature
        self.regenerate_metadata_signature(invalid_data["metadata"])
        
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("Errorcode"), 3012)
        
        print() 
        print("Test test_unreasonably_future_ntp_timestamp passed successfully!")
        
    def test_valid_ntp_timestamp(self):
        
        """測試合法的 NTP timestamp（接近現在）"""
        
        valid_data = copy.deepcopy(self.valid_firmware_data)

        # 設定為現在 ±5 秒範圍內的合法 NTP timestamp（使用與 views.py 一致的轉換邏輯）
        now = datetime.datetime.now(datetime.timezone.utc)
        ntp_epoch = datetime.datetime(1900, 1, 1, tzinfo=datetime.timezone.utc)
        current_ntp_timestamp = int((now - ntp_epoch).total_seconds())
        valid_data["metadata"]["release_date"] = current_ntp_timestamp
        
        # 重新生成 metadata_signature
        self.regenerate_metadata_signature(valid_data["metadata"])
        
        response = self.client.post(self.url, valid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json().get("UploadResult"), 1)
        
        print() 
        print("Test test_valid_ntp_timestamp passed successfully!")
    
    def test_blockchain_upload_fail(self):
        
        """測試 upload_to_blockchain 拋出例外時，API 回傳 500"""

        # 模擬 upload_to_blockchain 拋出 Exception
        with patch("upload_firmware.views.upload_to_blockchain") as mock_upload, \
            patch("time.sleep", return_value=None):  # 避免等待
            mock_upload.side_effect = Exception("Blockchain error")

            payload = copy.deepcopy(self.valid_firmware_data)
            response = self.client.post(self.url, payload, format="json")

            # 驗證回傳 HTTP 500
            self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

            print()
            print("Test test_blockchain_upload_fail passed successfully!")
    
    def test_manufacturer_upload_respond_signature_verification(self):
        
        """測試 ManufacturerUploadRespond 簽章是否有效"""
        
        import os
        import base64
        from cryptography.x509 import load_pem_x509_certificate

        # 使用 OpenSSL 產生的私鑰（你可切換 RSA/ECDSA）
        with open(MANUFACTURER_AGENT_PRIVATE_KEY_PATH, "rb") as f:
            agent_private_key = f.read()

        try:
            agent_private_key_str = agent_private_key.decode("utf-8")
        
        except UnicodeDecodeError as e:
            self.fail(f"私鑰 decode 失敗: {e}")

        payload = copy.deepcopy(self.valid_firmware_data)
        payload["agent_private_key"] = agent_private_key_str

        # 發送 POST 請求
        response = self.client.post(self.url, payload, format="json")
        json_data = response.json()

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 載入公鑰憑證
        self.assertTrue(os.path.exists(MANUFACTURER_AGENT_CERT_PATH), "公鑰憑證檔案不存在！")

        with open(MANUFACTURER_AGENT_CERT_PATH, "rb") as cert_file:
            cert = load_pem_x509_certificate(cert_file.read())
            public_key = cert.public_key()

        # 組合與簽章相同的原始資料
        errorcode_str = str(json_data['Errorcode']) if json_data['Errorcode'] is not None else ""
        raw_payload = f"{json_data['UploadResult']}|{json_data['Message']}|{errorcode_str}".encode()

        # 若回傳值簽章驗證失敗，將輸出: Signature 驗證失敗: cryptography.exceptions.InvalidSignature
        
        print() 
        print(f"[DEBUG] Payload to verify: {raw_payload.decode()}")
        
        try:
            signature = base64.b64decode(json_data["ManufacturerAgentSignature"], validate=True)
        except Exception as e:
            self.fail(f"Base64 解碼簽章失敗: {e}")

        try:
            if isinstance(public_key, rsa.RSAPublicKey):
                public_key.verify(signature, raw_payload, padding.PKCS1v15(), hashes.SHA256())
            elif isinstance(public_key, ec.EllipticCurvePublicKey):
                public_key.verify(signature, raw_payload, ec.ECDSA(hashes.SHA256()))
            else:
                raise TypeError("Unsupported public key type")
            
            # 確認演算法名稱正確
            self.assertIn(json_data["ManufacturerAgentSignatureAlgorithm"], ["RSA-SHA256", "ECDSA-SHA256"])
            
            print() 
            print(" Signature 驗證成功")
        
        except Exception as e:
            self.fail(f"Signature 驗證失敗: {e}")
