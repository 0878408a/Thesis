import os
from rest_framework.test import APITestCase
from rest_framework import status
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
import requests
from cryptography import x509 
from cryptography.hazmat.backends import default_backend 
# default_backend() 是一個函數，用於獲取當前可用的加密後端
from pathlib import Path
from django.test import SimpleTestCase # SimpleTestCase 才支援測試 TLS/mTLS


"""事前宣告私鑰及憑證路徑"""

USE_ECDSA = True  # 改成 False 即可改用 RSA 簽章測試

if USE_ECDSA:
    
    # 使用 NIST P-256 標準生成，金鑰長度 256 bits，強度等於 RSA 3072 bits
    MANUFACTURER_PRIVATE_KEY_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_manufacturer_private_key.pem")
    MANUFACTURER_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_manufacturer_public_cert.pem")
    MANUFACTURER_AGENT_PRIVATE_KEY_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_manufacturer_agent_private_key.pem")
    MANUFACTURER_AGENT_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_manufacturer_agent_public_cert.pem")

else:
    
    # 使用 RSA 4096 bits 生成
    MANUFACTURER_PRIVATE_KEY_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/manufacturer_private_key.pem")
    MANUFACTURER_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/manufacturer_public_cert.pem")
    MANUFACTURER_AGENT_PRIVATE_KEY_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/manufacturer_agent_private_key.pem")
    MANUFACTURER_AGENT_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/manufacturer_agent_public_cert.pem")

class UploadFirmwareTLSTestCase(SimpleTestCase):
    
    """TLS 憑證測試用例（不需啟動資料庫）"""

    def setUp(self):
        
        with open(MANUFACTURER_AGENT_CERT_PATH, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        
        self.cert_path = MANUFACTURER_AGENT_CERT_PATH
        self.server_url = "https://localhost:8000/upload_firmware/upload/"  

        # requests 做 mTLS 不需要開啟檔案，傳入路徑即可
        
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

    def test_tls_connection(self):
        
        """測試是否能透過 HTTPS 成功連線（驗證 TLS 建立）"""
        
        try:
            
            response = requests.get(self.server_url, verify = self.cert_path) 
            
            # 200 表示有 view 回應，404 表示路由存在但非 GET，405 表示路由存在，但用錯 HTTP 方法（例如用 GET 打 POST）
            # 這三種狀態碼都表示 TLS 連線成功
            
            self.assertIn(response.status_code, [200, 404, 405])  
            print() 
            print(f" 成功建立 TLS 連線，狀態碼：{response.status_code}")
        
        except requests.exceptions.SSLError as e:
            
            self.fail(f" TLS 憑證驗證失敗: {e}")
        
        except Exception as e:
            
            self.fail(f" 無法建立 TLS 連線: {e}")
            
    def test_mtls_connection(self):
        
        """測試是否能成功建立 mTLS 雙向驗證連線"""
        
        # 這裡使用 Werkzeug（Django Extensions）進行雙方認證測試，但這種內建的輕量測試環境僅能測試是否能交換雙方的憑證，無法讓後端驗證發送端的身分
        
        try:
            
            response = requests.get(
                self.server_url,
                cert=self.client_cert,  # 客戶端證書與私鑰
                verify=self.cert_path   # 驗證伺服器的憑證（自簽 CA）
            )
            
            self.assertIn(response.status_code, [200, 404, 405])
            print() 
            print(f" 成功建立 mTLS 連線，狀態碼：{response.status_code}")
        
        except requests.exceptions.SSLError as e:
            
            self.fail(f" mTLS 憑證驗證失敗: {e}")
        
        except Exception as e:
            
            self.fail(f" 無法建立 mTLS 連線: {e}")

class UploadFirmwareAPITestCase(APITestCase):
    
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
        
        Manufacturer = apps.get_model('register', 'Manufacturer')
        Device = apps.get_model('register', 'Device')
        
        '''
            先將資料庫內的 Manufacturer 資料取出來，
            get_or_create() 是 Django ORM 提供的方法
            主要用於：如果資料庫中已經存在符合條件的物件，則直接獲取它；如果物件不存在，則創建並回傳該物件
        
            get_or_create() 運作邏輯如下：
        
                用前面的參數當成查詢條件去 SELECT（這些通常是 unique 的）

                如果有找到，就直接回傳資料 + created=False

                如果找不到，就用這些條件 + defaults 合併來 INSERT
        '''
        
        self.manufacturer_id = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
        self.manufacturer, created = Manufacturer.objects.get_or_create(
            manufacturer_id=self.manufacturer_id,)
        '''
            defaults={
                "manufacturer_name": "AAA",
                "email": "123@AAA.COM",
                "manufacturer_cert": self.public_key
            }
        '''
         
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
        
        # 回傳值: created: True 表示是新建立的，False 表示是從資料庫撈出來的
        
        # print()
        # print(f"[DEBUG] Device created? {created}")
        
        
        # 導入 Customer 模型
        
        Customer = apps.get_model('register', 'Customer')

        
        # 將資料庫內的 Customer 資料取出來
        
        self.customer, created = Customer.objects.get_or_create(
            customer_id="3e01e6a7-1c25-4a5e-97c5-92ec5abfd10c",)
        '''
            defaults={
                "name": "ray",
                "email": "test@123.com",
                "manufacturer": self.manufacturer,
                "customer_cert": pem_cert_bytes  
            }
        '''
            
        
        # 回傳值: created: True 表示是新建立的，False 表示是從資料庫撈出來的
        
        # print()
        # print(f"[DEBUG] Customer created? {created}")
        
        '''
            print()
            print("[DEBUG] customer_cert raw bytes:", self.customer.customer_cert)
        
        
            # debug 用，印出來的 customer_cert 原始 bytes        
            
            try:
                cert = load_pem_x509_certificate(self.customer.customer_cert)
                pubkey = cert.public_key()
                
                print()
                print("[DEBUG] 解析成功 ")
            
            except Exception as e:
                
                print()
                print("[DEBUG] 解析失敗 ", e)
        '''
        
        # **產生 firmwaremetadata**
        
        # 轉換現在時間為 NTP timestamp
        now = datetime.datetime.now(datetime.timezone.utc)
        ntp_epoch = datetime.datetime(1900, 1, 1, tzinfo=datetime.timezone.utc)
        self.ntp_release_date = int((now - ntp_epoch).total_seconds())

        # 模擬 1024 bytes 的 firmware binary，再轉成 Base64 傳遞格式
        # 使用 len(self.firmware_binary) 讀取 binary 大小，方便更換測試資料

        self.firmware_binary = os.urandom(1024)
        self.firmware_size = len(self.firmware_binary)  
        self.firmware_version = "v1.0"
        self.correct_firmware_data = base64.b64encode(self.firmware_binary).decode()
        
        
        # 組合簽章原始資料（raw data，不先雜湊，因為 ECDSA 驗章會自動雜湊）
        
        signed_data = f"{self.firmware_size}{self.ntp_release_date}{self.manufacturer_id}{self.device.device_type}{self.firmware_version}".encode()

        # 判斷是 RSA 還是 ECDSA，並產生對應簽章與演算法名稱
        # isinstance() 用來檢查一個物件是否是某個特定類型，格式如下：
        # isinstance(變數, 類型)
        
        if isinstance(self.private_key, rsa.RSAPrivateKey):
            metadata_signature = self.private_key.sign(
                signed_data,  # 原始資料
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            firmware_signature = self.private_key.sign(
                signed_data,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            signature_algorithm = "RSA-SHA256"

        elif isinstance(self.private_key, ec.EllipticCurvePrivateKey):
            metadata_signature = self.private_key.sign(
                signed_data,
                ec.ECDSA(hashes.SHA256())  # 不需先雜湊，ECDSA 會自動處理
            )
            firmware_signature = self.private_key.sign(
                signed_data,
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
    
    # tearDown() 是 Django 測試框架 (unittest TestCase) 的方法，在每個測試方法 (test_xxx) 執行完後自動執行，用來清理測試過程中生成的數據。
    # 如果不手動寫 tearDown()，Django 還是會自動清除測試資料，但會保留資料庫的真實資料。
    
    '''
    def tearDown(self):
        
        """清理測試數據"""
        
        Manufacturer = apps.get_model('register', 'Manufacturer')
        Device = apps.get_model('register', 'Device')
        FirmwareMetadata = apps.get_model('upload_firmware', 'FirmwareMetadata')
        
        # 刪除 FirmwareMetadata 測試資料
        # .objects.all().delete() 是 Django ORM 提供的方法，
        # 主要用於：刪除資料表中的所有資料、適用於測試環境，快速清除測試資料、執行後不可恢復，請謹慎使用
        # self.manufacturer 是自行生成的 Manufacturer 測試資料，不會刪除資料庫的真實資料
        
        FirmwareMetadata.objects.filter(manufacturer=self.manufacturer).delete()
        Device.objects.filter(
            device_type=self.device.device_type,
            manufacturer=self.device.manufacturer
        ).delete()
        Manufacturer.objects.filter(manufacturer_id=self.manufacturer.manufacturer_id).delete()
    '''
    
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
        self.assertEqual(response.json().get("Message"), "Firmware uploaded successfully.")
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
            self.assertEqual(response.json().get("error_code"), error_code)
            
            print() 
            print(f"Test test_missing_metadata_field for {field} passed successfully!")
    
    def test_missing_firmware_data(self):
        """測試缺少 firmware_data 欄位（錯誤碼 3051）"""

        invalid_data = copy.deepcopy(self.valid_firmware_data)
        invalid_data.pop("firmware_data")

        response = self.client.post(self.url, invalid_data, format="json")
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("error_code"), 3051)

        print()
        print("Test test_missing_firmware_data passed successfully!")

            
    def test_invalid_base64_firmware_data(self):
        
        """測試 firmware_data 不是 base64"""
        
        # self.valid_firmware_data.copy() 
        # 使用.copy() 以便在測試時可以修改其中的數據，而不影響原始的 self.valid_firmware_data
        # 但.copy() 只複製最外層物件，copy.deepcopy()複製所有巢狀結構（遞迴）
        invalid_data = self.valid_firmware_data.copy()
        invalid_data["firmware_data"] = "Invalid@@Base64=="
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("error_code"), 3052)
        
        print() 
        print("Test test_invalid_base64_firmware_data passed successfully!")

    def test_invalid_metadata_base64(self):
        
        """測試 metadata_signature 不是 base64"""
        
        invalid_data = self.valid_firmware_data.copy()
        invalid_data["metadata"]["metadata_signature"] = "!!!not_base64$$$"
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("error_code"), 1013)
        
        print() 
        print("Test test_invalid_metadata_base64 passed successfully!")

    def test_invalid_firmware_signature_base64(self):
        """測試 firmware_signature 不是 base64（錯誤碼 2013）"""
        
        invalid_data = self.valid_firmware_data.copy()
        invalid_data["metadata"]["firmware_signature"] = "###not_base64@@@"
        
        response = self.client.post(self.url, invalid_data, format="json")
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("error_code"), 2013)

        print()
        print("Test test_invalid_firmware_signature_base64 passed successfully!")
    
    def test_firmware_size_mismatch(self):
        
        """測試 firmware_data 長度與 firmware_size 不符"""
        
        invalid_data = self.valid_firmware_data.copy()
        invalid_data["firmware_data"] = base64.b64encode(b"short_data").decode()
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("error_code"), 3053)
        
        print()
        print("Test test_firmware_size_mismatch passed successfully!")
        
    def test_metadata_signature_verification_fail(self):
        
        """測試 Metadata 簽章驗證失敗"""
        
        invalid_data = self.valid_firmware_data.copy()
        invalid_data["metadata"]["metadata_signature"] = base64.b64encode(b"wrong_signature").decode()
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("error_code"), 1012)
        
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
        self.assertEqual(response.json().get("error_code"), 2012)
        
        print() 
        print("Test test_firmware_signature_verification_fail passed successfully!")

            
    # @patch 來自 unittest.mock 模組，它的主要功能是用來模擬（mock）某些物件或函數的行為，
    # 以便測試不同的情境，例如：模擬資料庫錯誤
    
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
        self.assertEqual(response.json().get("error_code"), 1002)
        
        print()
        print("Test test_unsupported_signature_algorithm passed successfully!")

    def test_unsupported_firmware_signature_algorithm(self):
        
        """測試 firmware_signature_algorithm 不支援"""
        
        invalid_data = copy.deepcopy(self.valid_firmware_data)
        invalid_data["metadata"]["firmware_signature_algorithm"] = "bad_algo"
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("error_code"), 2002)
        
        print() 
        print("Test test_unsupported_firmware_signature_algorithm passed successfully!")
        
    def test_nonexistent_manufacturer_id(self):
        
        """測試 manufacturer_id 不存在資料庫中"""
        
        invalid_data = copy.deepcopy(self.valid_firmware_data)
        invalid_data["metadata"]["manufacturer_id"] = str(uuid.uuid4())  # 使用隨機 UUID 模擬不存在的 manufacturer
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.json().get("error_code"), 3023)
        print("Test test_nonexistent_manufacturer_id passed successfully!")

    def test_nonexistent_device_type(self):
        
        """測試 device_type 不存在資料庫中"""
        
        invalid_data = copy.deepcopy(self.valid_firmware_data)
        invalid_data["metadata"]["device_type"] = "NonExistentDevice"
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.json().get("error_code"), 3032)
        
        print() 
        print("Test test_nonexistent_device_type passed successfully!")

    from cryptography.hazmat.primitives.asymmetric import rsa, ec

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
                signed_data,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
        elif isinstance(self.private_key, ec.EllipticCurvePrivateKey):
            metadata_signature = self.private_key.sign(
                signed_data,
                ec.ECDSA(hashes.SHA256())
            )
            firmware_signature = self.private_key.sign(
                signed_data,
                ec.ECDSA(hashes.SHA256())
            )
        else:
            raise ValueError("Unsupported private key type")

        # 將簽章編碼為 Base64 字串
        payload["metadata"]["metadata_signature"] = base64.b64encode(metadata_signature).decode()
        payload["metadata"]["firmware_signature"] = base64.b64encode(firmware_signature).decode()

        return self.client.post(self.url, payload, format="json")

    def test_initial_firmware_version_valid(self):
        
        """初次上傳版本大於 0，應成功"""
        
        response = self.post_firmware("v1.0")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        print() 
        print("Test test_initial_firmware_version_valid passed successfully!")
        
    def test_initial_firmware_version_zero(self):
        
        """初次上傳版本為 v0.0，應失敗"""
        
        response = self.post_firmware("v0.0")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("error_code"), 3042)
        
        print() 
        print("Test test_initial_firmware_version_zero passed successfully!")

    def test_firmware_version_newer_than_existing(self):
        
        """上傳新版本高於已存在者，應成功"""
        
        self.post_firmware("v1.0")
        response = self.post_firmware("v2.0")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        print() 
        print("Test test_firmware_version_newer_than_existing passed successfully!")

    def test_firmware_version_equal_to_existing(self):
        
        """版本相同，應失敗"""
        
        self.post_firmware("v1.0")
        response = self.post_firmware("v1.0")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("error_code"), 3042)

        print() 
        print("Test test_firmware_version_equal_to_existing passed successfully!")
        
    def test_firmware_version_older_than_existing(self):
        
        """版本比現有小，應失敗"""
        
        self.post_firmware("v2.0")
        response = self.post_firmware("v1.0")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("error_code"), 3042)

        print() 
        print("Test test_firmware_version_older_than_existing passed successfully!")
        
        
    def test_invalid_uuid_format(self):
        
        """測試不合法的 UUID 格式"""
        
        invalid_data = copy.deepcopy(self.valid_firmware_data)
        invalid_data["metadata"]["manufacturer_id"] = "not-a-valid-uuid"
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("error_code"), 3022)
        
        print() 
        print("Test test_invalid_uuid_format passed successfully!")
    
    def test_negative_ntp_timestamp(self):
        
        """測試 NTP timestamp 為負值"""
        
        invalid_data = copy.deepcopy(self.valid_firmware_data)
        invalid_data["metadata"]["release_date"] = -100
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("error_code"), 3012)
        
        print() 
        print("Test test_negative_ntp_timestamp passed successfully!")

    def test_unreasonably_old_ntp_timestamp(self):
        
        """測試 release_date 為過舊時間（非現在）"""
        
        invalid_data = copy.deepcopy(self.valid_firmware_data)
        # 設為 1970-01-01 對應的 NTP timestamp（2208988800）
        invalid_data["metadata"]["release_date"] = 2208988800
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("error_code"), 3012)
        
        print() 
        print("Test test_unreasonably_old_ntp_timestamp passed successfully!")

    def test_unreasonably_future_ntp_timestamp(self):
        
        """測試 release_date 為未來時間（非現在）"""
        
        invalid_data = copy.deepcopy(self.valid_firmware_data)
        # 設為 2101-01-01 的 NTP timestamp（從 1900-01-01 起算秒數）
        future_ntp = int((datetime.datetime(2101, 1, 1, tzinfo=datetime.timezone.utc) - datetime.datetime(1900, 1, 1, tzinfo=datetime.timezone.utc)).total_seconds())
        invalid_data["metadata"]["release_date"] = future_ntp
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get("error_code"), 3012)
        
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
        response = self.client.post(self.url, valid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json().get("UploadResult"), 1)
        
        print() 
        print("Test test_valid_ntp_timestamp passed successfully!")
    
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
    '''
    def test_upload_triggers_blockchain_record(self):
        """測試 upload API 成功後自動觸發上鏈"""

        from submit_block.models import SubmitBlockRecord
        from upload_firmware.models import FirmwareMetadata

        # 使用 setUp 中已建立好的 self.valid_firmware_data 作為 payload
        payload = {
            "firmware_data": self.correct_firmware_data,
            "metadata": self.valid_firmware_data["metadata"]
        }

        # 發送 POST 請求
        response = self.client.post("/upload_firmware/upload/", payload, format="json")

        # 驗證 API 回應為 200 成功
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 使用 setUp 中已建立的 Customer 和 Device
        customer = self.customer
        metadata = FirmwareMetadata.objects.filter(
            firmware_version=self.firmware_version,
            device_type=self.device.device_type
        ).first()

        self.assertIsNotNone(metadata, "未建立對應的 FirmwareMetadata 資料")
        
        self.assertTrue(
            SubmitBlockRecord.objects.filter(metadata_id=metadata).exists(),
            "FirmwareMetadata 儲存後未成功上鏈"
        )
        
        print() 
        print(" Test test_upload_triggers_blockchain_record passed successfully!")

    def test_all_existing_customers_receive_block(self):
        """測試上傳韌體後所有相關客戶都上鏈（tag 為 customer_id）"""
        from submit_block.models import SubmitBlockRecord
        from upload_firmware.models import FirmwareMetadata
        from register.models import Customer

        # 建立第二個同一個 manufacturer 底下的 Customer（不再指定 device_type，改由後端查裝置）
        another_customer = Customer.objects.create(
            customer_id="123e4567-e89b-12d3-a456-426614174999",
            name="Another Customer",
            email="another@example.com",
            customer_cert=b'2' * 128,
            manufacturer=self.manufacturer
        )

        # 上傳韌體
        payload = {
            "firmware_data": self.correct_firmware_data,
            "metadata": self.valid_firmware_data["metadata"]
        }

        response = self.client.post("/upload_firmware/upload/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 查詢上傳成功的 metadata
        metadata = FirmwareMetadata.objects.filter(
            firmware_version=self.firmware_version,
            manufacturer=self.manufacturer,
            device_type=self.device.device_type
        ).first()
        self.assertIsNotNone(metadata)

        # 確認所有對應 customer 都有收到 SubmitBlockRecord 區塊紀錄（tag 為 customer_id）
        for cust in [self.customer, another_customer]:
            exists = SubmitBlockRecord.objects.filter(
                tag=cust.customer_id,
                metadata_id=metadata.id
            ).exists()
            self.assertTrue(exists, f"Customer {cust.customer_id} 未收到上鏈區塊")
        
        print() 
        print("Test test_all_existing_customers_receive_block passed successfully!")

    def test_new_customer_triggers_block_after_firmware_uploaded(self):
    
        """測試韌體已存在時，新增 Customer 會自動上鏈（透過 signal）"""
        from submit_block.models import SubmitBlockRecord
        from upload_firmware.models import FirmwareMetadata
        from register.models import Customer

        # 先上傳 firmware
        payload = {
            "firmware_data": self.correct_firmware_data,
            "metadata": self.valid_firmware_data["metadata"]
        }

        response = self.client.post("/upload_firmware/upload/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 檢查韌體是否已上傳成功
        metadata = FirmwareMetadata.objects.get(
            firmware_version=self.firmware_version,
            manufacturer=self.manufacturer,
            device_type=self.device.device_type
        )

        # 新增 Customer（應自動觸發上鏈 signal）
        new_customer = Customer.objects.create(
            customer_id="123e4567-e89b-12d3-a456-426614171234",
            name="Late Buyer",
            email="late@example.com",
            customer_cert=b'3' * 128,
            manufacturer=self.manufacturer
        )

        # 確保 signal 被觸發並成功新增 SubmitBlockRecord
        self.assertTrue(
            SubmitBlockRecord.objects.filter(tag=new_customer.customer_id, metadata_id=metadata.id).exists(),
            "新增 Customer 後未觸發上鏈"
        )

        print() 
        print("Test test_new_customer_triggers_block_after_firmware_uploaded passed successfully!")
        '''