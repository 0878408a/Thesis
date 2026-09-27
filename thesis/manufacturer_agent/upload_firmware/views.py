from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import base64
import uuid
import datetime
import time
import subprocess
import re
import shutil
from shared import config
from django.db.utils import IntegrityError # 這個模組提供了與資料庫相關的錯誤處理
from .models import Manufacturer, Device
from upload_firmware.models import FirmwareMetadata, SubmitBlockRecord
from cryptography.hazmat.primitives.asymmetric import rsa, ec, padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509 import load_pem_x509_certificate
from rest_framework import generics, serializers
from rest_framework.pagination import PageNumberPagination

'''
    運行 server 指令:
    
    python manage.py runserver 
    
    搭配憑證啟動 HTTPS / mTLS 支援
    
    python manage.py runserver_plus   --cert-file C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_manufacturer_agent_public_cert.pem   --key-file C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_manufacturer_agent_private_key.pem
'''

# 支援的簽章演算法別名（符合 RFC/NIST/OpenSSL 等標準命名）
SUPPORTED_SIGNATURE_ALGORITHMS = {
    
    # RSA with SHA-256（常見命名）
    "rsa": "RSA",
    "rsa-4096": "RSA",
    "rsa4096": "RSA",
    "rsa_pkcs1_sha256": "RSA",  # OpenSSL-style
    "rsa-sha256": "RSA",        # OpenSSH-style
    "rsassa-pkcs1-v1_5": "RSA", # RFC 8017 名稱

    # ECDSA with SHA-256（橢圓曲線簽章）
    "ecdsa": "ECDSA",
    "ecdsa-secp256r1": "ECDSA",      # NIST P-256 curve（又稱 prime256v1）
    "ecdsa-sha256": "ECDSA",         # SSH-style
    "ecdsa-with-SHA256": "ECDSA",    # OpenSSL 樣式（注意大小寫）
    "ecdsa-p256": "ECDSA",           # 簡化命名
    "es256": "ECDSA",                # COSE/JWT 常見縮寫（RFC 8152）
}

metadata_error_code = {
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

# 用於驗證 metadata 中 metadata 和 firmware 簽章欄位是否為合法 base64
base64_error_code = {
    "metadata_signature": 1013,
    "firmware_signature": 2013
}

# 函式 is_valid_base64() 定義: 檢查 Base64 格式欄位，用於驗證 metadata 中的簽章欄位和 firmware_data 是否為合法的 Base64 編碼，並回傳編碼後的資料
def is_valid_base64(value): 
            
    try:
                
        # Base64 編碼後的長度 一定是 4 的倍數（因為它是每 3 個 byte 轉成 4 個字元），如果不是 4 的倍數，就不可能是合法的 Base64 字串。
        # isinstance() 用來檢查一個物件是否是某個特定類型，格式如下：
        # isinstance(變數, 類型)
        # isinstance() 會檢查繼承關係，type() 反之，故實務上偏好使用 isinstance() 來檢查型別
        if not isinstance(value, str) or len(value) % 4 != 0:
                    
            # 如果失敗，回傳 False，不回傳任何資料 (None)
            return False, None
                
        # decode + validate=True 會確保：內容真的能解碼、沒有錯誤 padding
        decoded = base64.b64decode(value, validate=True) 
                
        # 驗證成功時，回傳 True 和解碼後資料 (decoded)
        return True, decoded  
            
    # binascii 是 Python 的內建模組之一，名稱來自 "Binary and ASCII" 的縮寫，專門處理：
    # 位元組（binary）與文字（ASCII）間的編碼與解碼。
    except (base64.binascii.Error, ValueError):
        return False, None

# 函式 verify_signature() 定義: 驗證簽章欄位（使用 Base64 編碼）
# firmware_binary=None 參數預設為 None，若要驗證韌體簽章才需要傳入 firmware_binary
def verify_signature(metadata_json, manufacturer_cert, signature_field, signature_bytes, firmware_binary = None):
        
    try:
        # 組合簽章原始資料
        # 根據是驗哪一種簽章來決定要組合哪種 raw_data
        if signature_field == "metadata_signature":
            raw_data = f"{metadata_json['firmware_size']}{metadata_json['release_date']}{metadata_json['manufacturer_id']}{metadata_json['device_type']}{metadata_json['firmware_version']}".encode() 
        elif signature_field == "firmware_signature":
            raw_data = firmware_binary
        
        # 從資料庫取出資料型態為 str 的 manufacturer_cert，轉換為.pem 的 bytes 格式，再取出公鑰
        if isinstance(manufacturer_cert, str):
            manufacturer_cert = manufacturer_cert.encode()
            
        # 從憑證中取出公鑰
        # load_pem_x509_certificate() 是 cryptography 函式庫提供的工具，
        # 傳入的參數必須是 bytes 型別（不是 string，要 .encode()）；
        # 解析後，cert 會是一個 x509.Certificate 物件
        cert = load_pem_x509_certificate(manufacturer_cert)
        
        # 從剛才的憑證 cert 中，提取公鑰。
        # 它會自動判斷是 RSA 或 ECDSA。
        # 回傳的 public_key 可用來進行簽章驗證（使用 verify() 方法呼叫）
        public_key = cert.public_key()

        # 根據演算法欄位進行驗章（支援 RSA / ECDSA）
        # 從 metadata_json 這個字典中取出 "metadata_signature_algorithm" 這個鍵的值，如果這個鍵不存在，就回傳預設的空字串 ""。
        # 因為簽章皆使用相同私鑰，所以選擇 metadata_signature_algorithm 判斷簽章算法就可以了
        algo = metadata_json.get("metadata_signature_algorithm", "").lower()
        
        # 使用正確的驗章演算法
        if SUPPORTED_SIGNATURE_ALGORITHMS[algo] == "RSA":
            # RSA 需要指定 padding，且須事先提供雜湊後的資料
            public_key.verify(signature_bytes, raw_data, padding.PKCS1v15(), hashes.SHA256())
            
        elif SUPPORTED_SIGNATURE_ALGORITHMS[algo] == "ECDSA":
            # ECDSA 驗章不需 padding，且會自動處理雜湊，若提供雜湊資料會出錯
            public_key.verify(signature_bytes, raw_data, ec.ECDSA(hashes.SHA256()))

        return True
        
    except Exception as e:
        
        print()
        print(f"[DEBUG] Signature verification failed: {e}")
        return False
    
# 函式 upload_to_blockchain() 定義: 上鏈邏輯，將 firmware_metadata 上鏈供 customer 查詢
def upload_to_blockchain(firmware_metadata, retry_interval=5, max_retries=None):
    
    '''
    不斷嘗試將 metadata 上鏈直到成功，或達到最大重試次數。
    
    參數:
    - manufacturer: manufacturer_id
    - device: 裝置型號
    - metadata_obj: FirmwareMetadata 資料
    - retry_interval: 每次重試間隔（秒）
    - max_retries: 最大重試次數，若為 None 則無限重試
    '''
    
    # 重試次數的計數器
    attempts = 0
    while True:
        
        object_id = None # 物件 ID，預設為 None，若上鏈成功會更新為實際的 object_id
        #npx_path = "C:/Users/User/AppData/Roaming/npm/npx.cmd"
        tsx_script_path = config.SUBMIT_FIRMWARE_TS_PATH
        
        # shutil 是 Python 標準函式庫中的一個模組，主要用於檔案與資料夾操作
        print(shutil.which("npx"))
        npx_path = shutil.which("npx")
        # shutil.which() 會在系統的 PATH 環境變數中搜尋指定的命令，並回傳其完整路徑
        if not npx_path:
            raise RuntimeError("找不到 npx，請確認已安裝 node/npm 並設定 PATH")
        try:
            # 組合 CLI 參數
            args = [ 
                # npx tsx 為 npm 套件，是一個可以直接執行 TypeScript .ts 檔案的命令，無需事先編譯成 JavaScript .js
                npx_path, "tsx", tsx_script_path,
                
                # 將資料轉成 UTF-8 編碼的 Python 字串
                # 簽章的 Raw signature bytes 不能直接 .decode('utf-8')，因為這些是隨機二進位值，不一定是合法 UTF-8，會報錯
                # base64.b64encode(...): 簽章欄位的 bytes 資料轉為可傳輸文字
                # .decode('utf-8'): 將 base64 bytes 變成字串以便 JSON 傳輸，使用 str 包含前綴 b'' 與 escape 字元，會導至驗章失敗
                str(firmware_metadata.metadata_signature_algorithm),
                base64.b64encode(firmware_metadata.metadata_signature).decode('utf-8'),
                str(firmware_metadata.firmware_signature_algorithm),
                base64.b64encode(firmware_metadata.firmware_signature).decode('utf-8'),
                str(firmware_metadata.firmware_size),
                str(firmware_metadata.release_date),
                str(firmware_metadata.manufacturer_id),
                str(firmware_metadata.device_type),
                str(firmware_metadata.firmware_version),
            ]

            # subprocess 是 Python 標準函式庫中的一個模組，主要用途是讓 Python 能夠呼叫外部指令或執行其他程式
            # 使用 subprocess.run() 帶入 args 執行 CLI 命令
            # capture_output=True 把執行結果的 stdout / stderr 都取出來儲存在 result.stdout / result.stderr 裡
            # capture_output 和 text 參數主要目的是讀取輸出的 objectId
            # text=True 將 stdout / stderr 轉為字串（預設是 bytes）
            # encoding="utf-8" 指定編碼格式為 UTF-8，避免 Windows 預設的 cp950 導致解碼錯誤
            result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")

            # result.returncode: 是外部程式結束時回傳給作業系統的狀態碼，也稱為 exit code，0 代表成功，非 0 代表失敗
            if result.returncode != 0:
                raise Exception(f"上鏈失敗: {result.stderr}")

            # 從 stdout 擷取 objectId
            # result.stdout：是用 subprocess.run(...) 執行 TypeScript 程式後的標準輸出（stdout），
            # 也就是 TypeScript 程式用 console.log(...) 印出來的內容。
            # re.search(...)：使用正規表示法（regular expression）在這段輸出中搜尋特定格式的文字。
            # r"OBJECT_ID:([a-zA-Z0-9x]+)"：
            # 這是匹配格式為 OBJECT_ID:xxx... 的字串
            #   OBJECT_ID: 是固定前綴
            #   ([a-zA-Z0-9x]+) 是捕捉 group，代表 objectId 的內容，
            #   允許的字元包括英文字母大小寫、數字、以及 x（像是 0xabc123...）
            match = re.search(r"OBJECT_ID:([a-zA-Z0-9x]+)", result.stdout)
            if not match:
                raise Exception("找不到 objectId，stdout: " + result.stdout)

            # 把 OBJECT_ID 內容這段字串「捕捉」起來，放在 group(1) 裡
            object_id = match.group(1)

            # 將上鏈的相關記錄及回傳結果存入資料庫
            SubmitBlockRecord.objects.create(
                object_id=object_id,
                metadata_id=firmware_metadata,
                submit_block_result=result.stdout,
            )

            print(f"[上鏈成功] object_id={object_id}, version={firmware_metadata.firmware_version}")
            break

        except Exception as e:
            print(f"[上鏈通知失敗]  object_id={object_id}， 錯誤：{e}")
            # 重試次數加 1
            attempts += 1
                        
            # 若設定最大重試次數，且已達上限，就放棄
            if max_retries is not None and attempts >= max_retries:
                print(f"[已達最大重試次數]  object_id={object_id}，停止重試")
                break
                        
            # 等待一段時間後重試
            time.sleep(retry_interval)

# 函式 ManufacturerUploadRespond() 定義: 封裝回傳訊息的格式，並支援 RSA / ECDSA 簽章（Base64 編碼）   
# http_status 參數預設為 400，若遇到其他錯誤 (如 404、500) 再傳入自訂的 http_status 
def ManufacturerUploadRespond(message, error_code=None, http_status=status.HTTP_400_BAD_REQUEST):
        
        '''
        封裝回傳格式，符合 ManufacturerUploadRespond 規格，並支援 RSA / ECDSA 簽章（Base64 編碼）
            - upload_result: 1 成功 / 0 失敗
            - message: 訊息
            - error_code: 錯誤代碼（None 表示無錯誤）
            - agent_private_key: 本機端的 manufacturer_agent 私鑰（PEM 字串）
        - http_status: HTTP 狀態碼（預設為 400，且獨立於簽章的封裝之外）
        '''
        # 從固定路徑載入 manufacturer_agent 私鑰，用於回傳訊息函式 ManufacturerUploadRespond() 的簽章
        agent_private_key_path  = config.MANUFACTURER_AGENT_PRIVATE_KEY_PATH
        agent_private_key  = agent_private_key_path.read_text() 
        
        # 如果 error_code 為 None，則 upload_result 設為 1，否則設為 0
        # 將錯誤碼轉換為字串，若上傳成功無錯誤碼為 None 時則設為空字串
        # 將 upload_result、message、error_code_str 這三個欄位組合成一個字串，並用 | 分隔後轉成 bytes，作為簽章用的資料。
        upload_result = 1 if error_code == None else 0
        error_code_str = str(error_code) if error_code is not None else ""
        payload = f"{upload_result}|{message}|{error_code_str}".encode()

        # [DEBUG] 用來確認簽章的資料是否成功上傳，1 代表成功，0 代表失敗，且失敗時會附上錯誤代碼，若無錯誤則為空字串
        print()
        print(f"[DEBUG] Payload to sign: {payload.decode()}")

        if agent_private_key:
            
            try:
                
                # 載入私鑰（支援 RSA 與 ECDSA）
                private_key = load_pem_private_key(agent_private_key.encode(), password=None)

                # 根據金鑰類型進行簽章
                if isinstance(private_key, rsa.RSAPrivateKey):
                    signature = private_key.sign(payload, padding.PKCS1v15(), hashes.SHA256())
                    algorithm = "RSA-SHA256"

                elif isinstance(private_key, ec.EllipticCurvePrivateKey):
                    signature = private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
                    algorithm = "ECDSA-SHA256"

                # 將位元組格式的簽章（bytes）轉成可傳輸的 Base64 字串
                signature_base64 = base64.b64encode(signature).decode()
                
            except Exception as e:
                
                print()
                print(f"[DEBUG] Signature creation failed: {e}")
                signature_base64 = ""
                algorithm = "SIGNING_FAILED"

        return Response({
            
            # 前三項來自 ManufacturerUploadRespond 參數，後兩項來自簽章結果
            "UploadResult": upload_result,
            "Message": message,
            "Errorcode": error_code if error_code else "",
            "ManufacturerAgentSignature": signature_base64,
            "ManufacturerAgentSignatureAlgorithm": algorithm
        
        }, status=status.HTTP_200_OK if upload_result else http_status)


# --- History API implementation (read-only listing of SubmitBlockRecord joined with FirmwareMetadata)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class SubmitBlockRecordHistorySerializer(serializers.ModelSerializer):
    firmware_version = serializers.CharField(source='metadata_id.firmware_version')
    device_type = serializers.CharField(source='metadata_id.device_type')
    firmware_size = serializers.IntegerField(source='metadata_id.firmware_size')
    release_date = serializers.IntegerField(source='metadata_id.release_date')

    class Meta:
        model = SubmitBlockRecord
        fields = [
            'object_id',
            'metadata_id',
            'firmware_version',
            'device_type',
            'firmware_size',
            'release_date',
            'submit_block_result',
        ]


class HistoryListAPIView(generics.ListAPIView):
    """GET /upload_firmware/history/

    Returns SubmitBlockRecord joined with FirmwareMetadata fields.
    Sorted by FirmwareMetadata.release_date DESC, then paginated.
    """
    serializer_class = SubmitBlockRecordHistorySerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        # select_related to avoid N+1 and order by related firmwaremetadata.release_date DESC
        return SubmitBlockRecord.objects.select_related('metadata_id').order_by('-metadata_id__release_date')


'''
    APIView 是 Django REST framework (DRF) 提供的一個基礎類別（Base class），專門用來建立基於 HTTP 方法的 API 邏輯
    
    UploadFirmwareAPIView 繼承了 APIView，從而獲得處理 HTTP 請求的基礎功能
    
    運作流程:
    
            [1] Client 端發送 POST 請求，Body 使用 JSON 格式字串
    

            [2] Django 透過 root project 中 urls.py 的 upload_firmware/ 解析對應到 upload_firmware/urls.py 中的： 
                path('upload/', UploadFirmwareAPIView.as_view())


            [3]  會透過 DRF 中 APIView 繼承的父類 .as_view() 建立 UploadFirmwareAPIView 的實例 
                ⤷ 這會回傳一個可處理 HTTP 請求的函式，內部會觸發 dispatch()

            [4] dispatch() 根據請求 method（POST），自動呼叫 self.post(request)，
                並從 UploadFirmwareAPIView 的實例到父類 APIView 找尋 def post(self, request) 方法

                同時 DRF 會:

                1:根據 Content-Type: application/json，會使用內建 JSONParser 來處理請求。

                2:這會將 request body 中的 JSON 字串，自動解析成 Python 字典。

                3:結果放入 request.data，可以直接使用 .get() 方法來取得資料。

            [5] 進入 UploadFirmwareAPIView 中的 def post(self, request) 執行邏輯: 
    
'''

class UploadFirmwareAPIView(APIView):
    
    '''
        處理韌體上傳請求，firmware metadata 上傳 json 格式範例如下：
        
        {
        "firmware_data": "ZGF0YQ==",                                   // LONGBLOB → base64 編碼後的韌體內容，最大約 4GB（不壓縮）
        "metadata": {
            "metadata_signature_algorithm": "rsa",                     // VARCHAR(255) → 簽章演算法（如 RSA, ECDSA）
            "metadata_signature": "YWJjZGVm",                          // VARBINARY(512) → ，metadata 的簽章值
            "firmware_signature_algorithm": "rsa",                     // VARCHAR(255) → 韌體簽章使用的演算法
            "firmware_signature": "Z2hpamts",                          // VARBINARY(512) → 為 base64 編碼 base64，韌體簽章值
            "firmware_size": 4,                                        // BIGINT(20) UNSIGNED → 韌體原始大小（單位：byte）
            "release_date": "3854745600",                              // BIGINT(20) → NTP timestamp，1900-01-01 起算秒數
            "manufacturer_id": "123e4567-e89b-12d3-a456-426614174000", // CHAR(36) → UUID v4 格式
            "device_type": "esp32",                                    // VARCHAR(100) → 裝置型號，如 esp32、arduino
            "firmware_version": "v1.1"                                 // VARCHAR(50) → 韌體版本編號
            }
        }

    '''
    
    # self 代表 class 的 instance，也就是 UploadFirmwareAPIView，用於存取 class 內部的屬性和方法  
    # request 是一個 HttpRequest 物件，代表「使用者送來的 HTTP 請求」
    def post(self, request):
        
        firmware_data = request.data.get("firmware_data", None) 
        metadata_json = request.data.get("metadata", None)

        # 檢查資料是否存在
        if not metadata_json:
            
            return ManufacturerUploadRespond("FirmwareMetadata 欄位缺失",1000)
        # metadata 必須是 dict
        if not isinstance(metadata_json, dict):
            return ManufacturerUploadRespond("FirmwareMetadata 格式錯誤，必須為 JSON object", 1003)
        
        if not firmware_data:
            
            return ManufacturerUploadRespond("FirmwareData 欄位缺失",3051 )
        
        # 檢查 metadata 缺少欄位
        # datatype = list
        # 檢查欄位是否缺失或值為 None / 空字串 / 空值（如 ""、None）
        missing_fields = [
            field for field in metadata_error_code
            if field not in metadata_json or metadata_json[field] in [None, ""]
        ]

        if missing_fields:
            
            # 將所有缺失或空值欄位列出，儲存成 dict，並標明錯誤碼與欄位名
            error_details = [
                {
                    "field": field,
                    "error_code": metadata_error_code[field],
                    "message": f"{field} 欄位缺失"
                }
                for field in missing_fields
            ]

            return ManufacturerUploadRespond(          
                # 將所有缺失的欄位和 error code 印出 
                error_details,
                1001
            )
            
        # 驗證簽章演算法是否支援
        # 傳入的簽章演算法名稱資料型態為字串，轉成小寫後與支援的演算法進行比對
        sig_algo = metadata_json["metadata_signature_algorithm"].lower()
        if sig_algo not in SUPPORTED_SIGNATURE_ALGORITHMS:
            return ManufacturerUploadRespond("韌體 metadata 簽章為不支援的數位簽章演算法", 1002)

        sig_algo_fw = metadata_json["firmware_signature_algorithm"].lower()
        if sig_algo_fw not in SUPPORTED_SIGNATURE_ALGORITHMS:
            return ManufacturerUploadRespond("韌體簽章為不支援的數位簽章演算法", 2002)

        # 檢查 metadata_signature 和 firmware_signature 欄位是否為合法 base64
        # 逐一處理 base64_error_code 字典中的每一組欄位 field 與錯誤碼 error_code 。
        decoded_fields = {}
        
        # .items() 是 Python 字典（dict）的內建方法，用來同時取得鍵（key）與對應的值（value），非常適合用在 for 迴圈中逐一處理每個欄位與其對應資料。
        for field, error_code in base64_error_code.items():
            
            # valid 接收回傳值 → True/False（代表有沒有通過 base64 驗證）
            # decoded → 接收解碼後回傳的 bytes（如果有成功），否則回傳 None
            valid, decoded = is_valid_base64(metadata_json[field])
            
            if not valid:    
                return ManufacturerUploadRespond(f"簽章須為 base64 編碼: {field}", error_code)
            
            # 如果驗證成功，將解碼後的資料儲存到 decoded_fields 字典中
            # 後續存入資料庫時可用 decoded_fields["metadata_signature"] 或 decoded_fields["firmware_signature"] 取值
            decoded_fields[field] = decoded
        
        # 驗證 firmware_data 是否為合法 base64
        if not is_valid_base64(firmware_data):    
            return ManufacturerUploadRespond( "FirmwareData 須為 base64 編碼", 3052)

        # 驗證 manufacturer_id UUID 格式驗證
        try:
            
            # uuid.UUID() 會嘗試把前端傳過來的 manufacturer_id 當成 UUID 物件解析，如果格式不合法會丟出例外
            uuid.UUID(metadata_json["manufacturer_id"])
        
        except (ValueError, TypeError):    
            return ManufacturerUploadRespond("ManufacturerID 長度或資料型態錯誤", 3022)
        
        # 驗證 Device_type、 Manufacturer_id 是否存在資料庫
        # 若以下這兩筆資料不存在(Manufacturer 和 Device)，無法將 FirmwareMetadata 儲存進資料庫，因為它們是 Foreign Key（外鍵關聯）欄位。
        # (假設資料庫中已註冊這兩筆資料)
        # Manufacturer.objects 代表要查詢的 Model 表格（Django ORM），
        # filter() 相當於在資料庫裡幫你用 WHERE 條件查詢，找出符合條件的多筆資料
        # first() 取得第一筆資料
        manufacturer = Manufacturer.objects.filter(manufacturer_id=metadata_json["manufacturer_id"]).first()
        if not manufacturer:
            return ManufacturerUploadRespond("ManufacturerID 不存在資料庫", 3023, status.HTTP_404_NOT_FOUND)
        
        # upload_firmware/modles.py 的 Device 資料表就是使用 manufacturer 物件外鍵關連到 manufacturer 的資料表，所以 views.py 要相對應 
        device = Device.objects.filter( 
            device_type=metadata_json["device_type"],
            manufacturer_id=manufacturer.manufacturer_id
        ).first()
        
        if not device:
            return ManufacturerUploadRespond("DeviceType 不存在資料庫", 3032, status.HTTP_404_NOT_FOUND)

        # NTP Timestamp 格式驗證
        try:
            # 取得資料庫中 device + manufacturer 對應的最新韌體
            # filter() 相當於在資料庫裡幫你用 WHERE 條件查詢，找出符合條件的多筆資料，
            # .order_by() 是用來排序查詢結果的函式，對應到底層 SQL 的 ORDER BY 子句。
            # release_date 前面加上 "-" 表示 降冪（Descending），所以資料會依照日期從「最新」排到「最舊」
            # first() 取得第一筆資料
            latest_firmware = FirmwareMetadata.objects.filter(
                manufacturer_id=manufacturer.manufacturer_id,
                device_type=device.device_type,
            ).order_by("-release_date").first() 
            
            from django.db import connection
            # print(connection.queries[-1])  # 印出最近一筆 SQL 查詢
            
            release_timestamp = int(metadata_json["release_date"]) 
                
            '''
                datetime 套件的 API 背後都還是基於 Unix 時間戳（1970 起算）
                所以要轉換成 NTP Timestamp 1900 年 1 月 1 日 開始計算的格式
                datetime.datetime.now(datetime.timezone.utc) 取得當前 UTC 時間
                datetime.datetime(1900, 1, 1, tzinfo=datetime.timezone.utc) 取得 NTP 時間戳的起始時間
                total_seconds() 取得兩者之間的秒數差
                int() 轉換成整數，這樣就可以得到 NTP 時間戳格式
            '''
                
            now_ntp_timestamp = int((datetime.datetime.now(datetime.timezone.utc) - datetime.datetime(1900, 1, 1, tzinfo=datetime.timezone.utc)).total_seconds())
            
            #print(f"[DEBUG] db_latest_release: {db_latest_release}")
            #print(f"[DEBUG] release_timestamp: {release_timestamp}")
            print(f"[DEBUG] now_ntp_timestamp: {now_ntp_timestamp}")
            
            # 如果資料庫已有舊版韌體
            if latest_firmware:
                db_latest_release = latest_firmware.release_date
                
                # release_ts 必須大於或等於資料庫最新 release_date，且小於等於現在時間
                if not (db_latest_release <= release_timestamp <= now_ntp_timestamp):    
                    return ManufacturerUploadRespond("release_date 必須介於資料庫最新韌體 release_date 與現在時間之間", 3012)

            # 允許誤差範圍±10 秒內
            '''
                即使兩邊都轉成「NTP timestamp（1900 起算）」：

                客戶端計算時間點 → 傳送過網路

                伺服器再接收到 → now_ntp_timestamp 是更晚的時間

                這段過程中 即使使用的是正確演算法，也會出現秒數差異。
            '''
            ALLOWED_TIME_DRIFT = 10
                
            # 如果資料庫沒有舊版韌體，只需要檢查 release_date 不超過現在時間
            if not release_timestamp < now_ntp_timestamp + ALLOWED_TIME_DRIFT:                    
                return ManufacturerUploadRespond("release_date 不可大於現在時間", 3012)

        except (ValueError, TypeError):    
            return ManufacturerUploadRespond("release_date 格式錯誤或無效", 3012)
        
        # 驗證 FirmwareVersion 版本號是否與目前資料庫最新的版本重複
        # 取得目前資料庫中 device_type + manufacturer 對應的韌體
        # FirmwareMetadata.objects 代表要查詢的 Model 表格（Django ORM）
        # filter() 相當於在資料庫裡幫你用 WHERE 條件查詢，找出符合條件的多筆資料，
        # 查詢是否已有該版本號存在（同一個廠商 + 裝置）
        # 當 Django ORM 使用 .exists() 時會產生一條 SQL 查詢，如:
        '''
            SELECT 1 AS "a"     // 只想知道是否有資料存在，只要傳一個值（比如數字 1）就好，並幫這個值取名叫 "a"
            FROM "upload_firmware_firmwaremetadata" 
            WHERE "upload_firmware_firmwaremetadata"."manufacturer_id" = '123e4567-e89b-12d3-a456-426614174000' 
            AND "upload_firmware_firmwaremetadata"."device_type" = 'esp32' 
            AND "upload_firmware_firmwaremetadata"."firmware_version" = 'v1.2' 
            LIMIT 1;    // 一旦資料庫找到第一筆符合條件的紀錄，就會立即停止查詢，節省資源。
        '''
        incoming_version = (metadata_json["firmware_version"])
        
        existing_version = FirmwareMetadata.objects.filter(
            manufacturer_id=manufacturer.manufacturer_id,
            device_type=device.device_type,
            firmware_version=incoming_version
        ).exists()  
        
        if existing_version:
            return ManufacturerUploadRespond("FirmwareVersion 版本號重複", 3042)

        # 檢查 FirmwareData 是否為合法 base64，以及檢查 FirmwareData 長度是否與 FirmwareSize 相符
        valid, firmware_binary = is_valid_base64(firmware_data)
        if not valid:
            return ManufacturerUploadRespond("FirmwareData 須為 base64 編碼", 3052)
        
        try:
            firmware_size = int(metadata_json.get("firmware_size"))
        except (ValueError, TypeError):
            return ManufacturerUploadRespond("FirmwareSize 格式錯誤或型別不正確", 3050)
        
        # len() 是 Python 的內建函式，用來取得：
        # 序列（如字串、串列、位元組...）或集合物件的長度
        if len(firmware_binary) != firmware_size:
            return ManufacturerUploadRespond("Firmware size mismatch.", 3053)
        
        # 呼叫 verify_signature() 函式進行簽章驗證
        # 已從驗證 Manufacturer_id 是否存在資料庫取得 manufacturer 物件，可直接存取 manufacturer_cert 欄位
        if not verify_signature(metadata_json, manufacturer.manufacturer_cert, "metadata_signature", decoded_fields["metadata_signature"]):
            return ManufacturerUploadRespond("Metadata signature verification failed.", 1012)

        if not verify_signature(metadata_json, manufacturer.manufacturer_cert, "firmware_signature", decoded_fields["firmware_signature"], firmware_binary=firmware_binary):
            return ManufacturerUploadRespond("Firmware signature verification failed.", 2012)
        
        try:
            # 資料儲存 
            # .objects.create(...) 是 Django ORM（Object-Relational Mapping）提供的一個快捷方法，用來建立資料並直接儲存到資料庫。 
            # 使用.objects.create 將資料儲存到 FirmwareMetadata 資料表中      
            firmware_metadata = FirmwareMetadata.objects.create( 
                metadata_signature=decoded_fields["metadata_signature"],
                metadata_signature_algorithm=metadata_json["metadata_signature_algorithm"],
                firmware_signature=decoded_fields["firmware_signature"],
                firmware_signature_algorithm=metadata_json["firmware_signature_algorithm"],
                firmware_size=int(metadata_json["firmware_size"]),
                release_date=int(metadata_json["release_date"]),
                manufacturer_id=manufacturer.manufacturer_id,
                device_type=device.device_type,
                firmware_version=metadata_json["firmware_version"],
                firmware_data=firmware_binary
            )    

        # 韌體相關資料儲存若有錯誤回傳 Database error 5001
        # IntegrityError 是 Django ORM 中的一個例外類型，通常用來處理資料庫的完整性約束錯誤，例如唯一性約束違反、外鍵約束違反等。
        except IntegrityError as e:
            return ManufacturerUploadRespond(f"Database error: {str(e)}", 5001)
        except Exception as e:
            return ManufacturerUploadRespond(f"Database Unexpected error: {str(e)}", 5002)
        
        # 成功存入資料庫後，將 firmware_metadata 上鏈供 customer 查詢
        try:
            upload_to_blockchain(firmware_metadata)
             # 上傳成功需回傳 Response() 給 Client，若無設定使 Django 回傳 None，則違反 DRF 的規定，會報錯。
            return ManufacturerUploadRespond("Firmware uploaded successfully")
        except Exception as e:
            print(f"[上鏈失敗] {e}")
            # 回傳 500 並把錯誤訊息傳給前端
            return ManufacturerUploadRespond(
                message=str(e),
                error_code=500,
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    