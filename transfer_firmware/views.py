from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Manufacturer, Device, Customer
from upload_firmware.models import FirmwareMetadata
from django.http import FileResponse, JsonResponse
# download_firmware() 函式定義在 APIView() 之外，不支援 DRF 的 Response 只能用 JsonResponse
from django.core.cache import cache
from django.core.files.base import ContentFile
import base64 
import hashlib
import time
import uuid
import io
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509 import load_pem_x509_certificate


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
    "ecdsa-with-sha256": "ECDSA",    # OpenSSL 樣式（注意大小寫）
    "ecdsa-p256": "ECDSA",           # 簡化命名
    "es256": "ECDSA",                # COSE/JWT 常見縮寫（RFC 8152）
}

request_error_code = {
    "customer_signature_algorithm":4001,
    "customer_signature":4011,
    "customer_id":4021, 
    "manufacturer_id": 4032,
    "device_type":4041, 
    "firmware_version":4051, 
}

# 函式 verify_signature() 定義: 驗證簽章欄位（使用 Base64 編碼)  
def verify_signature(customer_cert, customer_signature_decoded, manufacturer_id, device_type, firmware_version, customer_id, signature_algorithm):
    try:
        # 組合簽章原始資料
        raw_data = f"{manufacturer_id}{device_type}{firmware_version}{customer_id}".encode()

        # 從憑證中取出公鑰
        # load_pem_x509_certificate() 是 cryptography 函式庫提供的工具，
        # 傳入的參數必須是 bytes 型別（不是 string，要 .encode()）；
        # 解析後，cert 會是一個 x509.Certificate 物件
        cert = load_pem_x509_certificate(customer_cert)
        
        # 從剛才的憑證 cert 中，提取公鑰。
        # 它會自動判斷是 RSA 或 ECDSA。
        # 回傳的 public_key 可用來進行簽章驗證（使用 verify_signature() 方法呼叫）
        public_key = cert.public_key()

        if signature_algorithm.lower() == "rsa":
            public_key.verify(customer_signature_decoded, raw_data, padding.PKCS1v15(), hashes.SHA256())
        elif signature_algorithm.lower() == "ecdsa":
            public_key.verify(customer_signature_decoded, raw_data, ec.ECDSA(hashes.SHA256()))
        else:
            return False

        return True
    except Exception as e:
            
        print()
        print("[DEBUG] Signature verification failed:", e)
        return False
    
# 函式 def generate_signed_url() 定義: 透過 Django 快取系統（cache）生成一次性 URL
# 可以用 ThreadPoolExecutor（執行緒池）來避免效能瓶頸
def generate_signed_url(manufacturer_id: str, device_type: str, firmware_version: str, validity_seconds: int = 300):

    '''
        產生一次性下載 URL，並將查詢條件寫入快取。

    Args:
        manufacturer_id (str): 製造商 UUID
        device_type (str): 裝置型號
        firmware_version (str): 韌體版本
        validity_seconds (int): 有效秒數，預設 300 秒

    Returns:
        str: 完整下載 URL
    '''
    # 計算到期時間
    # time.time()：取得目前系統時間（Unix timestamp，單位是秒，浮點數）
    # int(...)：轉成整數秒，加上 validity_seconds（預設是 300 秒，也就是 5 分鐘）
    # payload["expires_at"] 就是有效期限的截止時間戳 
    expires_at = int(time.time()) + validity_seconds
    
    # 使用 uuid4 產生隨機 token
    token = uuid.uuid4().hex

    # 寫入快取，讓下載 API 根據參數查詢韌體，並驗證 token 是否有效（有效期 = expires_at）
    cache.set(token, {
        "expires_at": expires_at,
        "manufacturer_id": manufacturer_id,
        "device_type": device_type,
        "firmware_version": firmware_version
    }, timeout=validity_seconds)
    
    '''
        cache.set(...): Django 提供的快取系統函式，用來儲存資料。
                        預設會使用你在 settings.py 中設定的快取 backend（如：Memcached、Redis、本機記憶體等）

        token: 一次性下載 URL 的唯一識別碼（例如 uuid4().hex）
        
        {"expires_at": expires_at}: 快取中儲存的 payload，可包含過期時間、請求資訊等（可以自由擴充）
        
        timeout=validity_seconds: 設定這筆快取在多少秒後自動失效（過期）
    '''

    url = f"https://localhost:8000/transfer_firmware/download/{token}/"
    return url

# 函式 def download_firmware() 定義: customer 透過 URL 請求下載韌體檔案的檢查與回傳邏輯
# 在 transfer_firmware/urls.py 中註冊下載 URL 路徑： path("download/<str:token>/", download_firmware) 即可正常使用
def download_firmware(request, token):
    '''
    驗證 token 是否存在於快取，並檢查是否過期與合法。
    合法的 token 對應 payload，若存在則允許下載韌體並將 token 作廢。
    '''
    # 檢查該 token 是否還存在於快取中，如果找不到，表示這個 token 已經過期或不存在
    # 如果這個 token 是用 generate_signed_url() 產生並寫入快取的，它會對應一份資料，例如：
    '''
        {
            "expires_at": 1714900000,
            "timeout": "300",
            ...
        }
    '''
    payload = cache.get(token)
    if not payload:
        return JsonResponse({"message": "無效或已過期的 URL"}, status=status.HTTP_403_FORBIDDEN)

    # 檢查過期時間
    # 用 int(time.time()) 取得目前時間戳，比較是否超時
    expires_at = payload.get("expires_at")
    now = int(time.time())
    if now > expires_at:
        return JsonResponse({"message": "該 URL 已過期"}, status=status.HTTP_403_FORBIDDEN)

    # 標記某個 token（一次性 URL）是否已經被使用過
    '''
        假設 token 是："abc123"，那麼 cache 中會有一個鍵值對：
        當 token 被使用 "used_token:abc123" → True
        避免 URL 被重複使用 
    '''
    used_key = f"used_token:{token}"
    if cache.get(used_key):
        return JsonResponse({"message":"該 URL 已被使用"}, status=status.HTTP_403_FORBIDDEN)

    # 一旦確認 URL 可被下載，就馬上標記為已使用
    cache.set(used_key, True, timeout=3600)  # 設定 1 小時內都不能重用這個 token

    # 根據 payload 決定 firmware 檔案
    # 從 payload 中提取查詢條件
    manufacturer_id = payload.get("manufacturer_id")
    device_type = payload.get("device_type")
    firmware_version = payload.get("firmware_version")

    # 從 DB 查詢 FirmwareMetadata
    manufacturer = Manufacturer.objects.filter(manufacturer_id=manufacturer_id).first()
    metadata = FirmwareMetadata.objects.filter(
         manufacturer_id=manufacturer.manufacturer_id,
        device_type=device_type,
        firmware_version=firmware_version
    ).first()

    if not metadata or not metadata.firmware_data:
        return JsonResponse({"message":"找不到對應的韌體資料"}, status=status.HTTP_404_NOT_FOUND)

    # 使用 ContentFile 將 bytes 資料轉為檔案形式
    # ContentFile 是 Django 提供的一種「將 bytes 封裝成檔案物件」的工具
    # 用 io.BytesIO() 將其包裝為 byte stream，這是 FileResponse 所需的格式
    firmware_file = ContentFile(metadata.firmware_data)
    firmware_file_io = io.BytesIO(firmware_file.read())

    # 使用 Django 的 FileResponse 將這個 byte stream 回傳給使用者
    # as_attachment=True 表示這是下載用的檔案
    return FileResponse(
        firmware_file_io,
        as_attachment=True,
        filename=f"{manufacturer_id}_{device_type}_{firmware_version}.bin"
    )
    
# 函式 def response_with_signature() 定義: 封裝回傳訊息的格式，並支援 RSA / ECDSA 簽章（Base64 編碼） 
def response_with_signature(message, error_code=None, url=None, http_status=status.HTTP_400_BAD_REQUEST):
    
    '''
    封裝回傳格式，符合 DownloadFirmware Response 規格，並支援 RSA / ECDSA 簽章（Base64 編碼）
        - message: 訊息內容
        - error_code: 錯誤代碼（None 表示成功）
        - url: 若成功，附上下載網址
    - http_status: 回傳的 HTTP 狀態碼（預設為 400）
    '''

    # 從固定路徑載入 manufacturer_agent 私鑰，用於回傳訊息函式 ManufacturerUploadRespond() 的簽章
    # MANUFACTURER_AGENT_PRIVATE_KEY_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/manufacturer_agent_private_key.pem")

    # 若要改用 ECDSA，只要註解上面一行，打開這一行即可：
    MANUFACTURER_AGENT_PRIVATE_KEY_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_manufacturer_agent_private_key.pem")
    agent_private_key  = MANUFACTURER_AGENT_PRIVATE_KEY_PATH.read_text()

    
    # 是否成功（用於 payload 與 UploadResult 欄位）
    upload_result = 1 if error_code is None else 0
    
    # 組成 payload 進行簽章
    # 如果 error_code 有值（不是 None）→ 把它轉成字串並指派給 err_str
    # 如果 error_code 是 None → 指派空字串 "" 給 err_str
    err_str = str(error_code) if error_code is not None else ""
    # 如果 url 有值且非空 → 指派原本的 url
    # 如果 url 是 None 或空字串 → 指派 "" 空字串
    url_str = url if url else ""
    raw_payload = f"{upload_result}|{url_str}|{message}|{err_str}".encode()
            
    print()
    print(f"[DEBUG] Payload to sign: {raw_payload.decode()}")

    private_key = load_pem_private_key(agent_private_key.encode(), password=None)
        
    if isinstance(private_key, rsa.RSAPrivateKey):
        signature = private_key.sign(raw_payload, padding.PKCS1v15(), hashes.SHA256())
        algorithm = "RSA-SHA256"
    elif isinstance(private_key, ec.EllipticCurvePrivateKey):
        signature = private_key.sign(raw_payload, ec.ECDSA(hashes.SHA256()))
        algorithm = "ECDSA-SHA256"

    return Response({
        "ResponseResult": upload_result,
        "ResponseURL": url_str,
        "Message": message,
        "Errorcode": error_code if error_code else "",
        "ManufacturerAgentSignature": base64.b64encode(signature).decode(),
        "ManufacturerAgentSignatureAlgorithm": algorithm
    }, status=status.HTTP_201_CREATED  if upload_result else http_status)

class FirmwareDownloadRequestAPIView(APIView):
    '''處理韌體下載請求'''

    def post(self, request):
        
        # 取得 request 欄位
        customer_id = request.data.get("customer_id")
        manufacturer_id = request.data.get("manufacturer_id")
        device_type = request.data.get("device_type")
        firmware_version = request.data.get("firmware_version")
        customer_signature_algorithm = request.data.get("customer_signature_algorithm")
        customer_signature = request.data.get("customer_signature")
    
        # 檢查 request_field 缺少欄位
        # datatype = list
        # 檢查欄位是否缺失或值為 None / 空字串 / 空值（如 ""、None）
        missing_fields = [
            field for field in request_error_code
            if request.data.get(field) in [None, ""]
        ]

        if missing_fields:
            
            # 將所有缺失或空值欄位列出，儲存成 dict，並標明錯誤碼與欄位名
            error_details = [
                {
                    "field": field,
                    "error_code": request_error_code[field],
                    "message": f"{field} 欄位缺失"
                }
                for field in missing_fields
            ]

            return response_with_signature(          
                # 將所有缺失的欄位和 error code 印出 
                error_details,
                4001
            )
                
        # 驗證 Customer 是否存在
        # 會被 Django ORM 轉成如下的 SQL 查詢：
        # SELECT * FROM customer WHERE customer_id = 'xxxxxx....';
        customer = Customer.objects.filter(customer_id=customer_id).first()
        if not customer:
            return response_with_signature("CustomerID 不存在資料庫", 4022)

        # 驗證 manufacturer_id 是否存在
        manufacturer = Manufacturer.objects.filter(manufacturer_id=manufacturer_id).first()
        if not manufacturer:
            return response_with_signature("ManufacturerID 不存在資料庫", 4032)

        # 驗證 Device 是否存在
        device = Device.objects.filter(device_type=device_type, manufacturer_id=manufacturer.manufacturer_id).first()
        if not device:
            return response_with_signature("DeviceType 不存在資料庫", 4042)

        # 驗證 Firmware 是否存在
        firmware = FirmwareMetadata.objects.filter(device_type=device.device_type, manufacturer_id=manufacturer.manufacturer_id, firmware_version=firmware_version).first()
        if not firmware:
            return response_with_signature("FirmwareVersion 不存在資料庫", 4052)


        # 驗證簽章演算法是否支援
        if customer_signature_algorithm.lower() not in SUPPORTED_SIGNATURE_ALGORITHMS:
            return response_with_signature("不支援的數位簽章或雜湊演算法", 4002)
            
        # 檢查 customer_signature 欄位是否為合法 base64
        try:
            # valid 接收回傳值 → True/False（代表有沒有通過 base64 驗證）
            # decoded → 接收解碼後回傳的 bytes（如果有成功），否則回傳 None
            customer_signature_decoded = base64.b64decode(customer_signature, validate=True)
            
        except (base64.binascii.Error, ValueError):    
            return response_with_signature("簽章須為 base64 編碼", 4012)
            
        # 呼叫 verify_signature 驗證 customer_signature
        if not verify_signature(
            customer.customer_cert,
            customer_signature_decoded,
            manufacturer.manufacturer_id,
            device_type,
            firmware_version,
            customer_id,
            customer_signature_algorithm
        ):
            return response_with_signature("數位簽章驗證失敗", 4012)
            
        # 回傳一次性url
        download_url = generate_signed_url(
            manufacturer_id=manufacturer.manufacturer_id,
            device_type=device.device_type,
            firmware_version=firmware_version
        )

        # 成功回應
        return response_with_signature(
            "Download approved.",
            None,
            url=download_url
        )
    
    