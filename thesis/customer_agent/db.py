import os
import pymysql
from pymysql.cursors import DictCursor
# DictCursor：設定游標的回傳格式為「字典形式」，讓查詢結果像這樣：
# {"manufacturer_id": "xxx", "device_type": "esp32"}
from dotenv import load_dotenv

# 資料庫設定
# 載入 .env
load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "charset": "utf8mb4",
    "cursorclass": DictCursor,
}

def get_db_connection():
    # 把 DB_CONFIG 解開作為 pymysql.connect() 的參數
    return pymysql.connect(**DB_CONFIG)

# 查詢所有 device 資料表對應的 manufacturer_id 與 device_type
def get_all_devices():
    with get_db_connection() as conn: 
        # 自動管理資料庫連線資源，加上 with 使用完後會自動 .close() 連線
        with conn.cursor() as cursor:
            # 游標（cursor）用來操作 SQL 語句控制物件，加上 with 使用完後會自動 .close() 游標
            cursor.execute("SELECT manufacturer_id, device_type FROM device")
            return cursor.fetchall()
            # 一次性取得查詢結果的所有資料列（rows）
        '''
            會回傳一個像這樣的結果：
                
            [
                {"name": "Alice", "email": "alice@example.com"},
                {"name": "Bob", "email": "bob@example.com"},
                {"name": "Charlie", "email": "charlie@example.com"}
            ]

        '''

# 確認指定版本是否已存在於資料庫中
def firmware_exists(manufacturer_id, device_type, firmware_version):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            sql = """
            SELECT 1 FROM firmwaremetadata
            WHERE manufacturer_id = %s AND device_type = %s AND firmware_version = %s
            LIMIT 1
            """
            cursor.execute(sql, (manufacturer_id, device_type, firmware_version))
            return cursor.fetchone() is not None

# 寫入查詢結果至 firmwaremetadata 表格
def insert_firmware_metadata(object_id, metadata, firmware_data=b""):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            sql = """
            INSERT INTO firmwaremetadata (
                object_id, metadata_signature, metadata_signature_algorithm,
                firmware_signature, firmware_signature_algorithm,
                firmware_size, release_date, manufacturer_id,
                device_type, firmware_version, firmware_data
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            # 會在執行時再填入對應的參數，這裡的 %s 會被後面的 tuple 中的值按順序填入
            cursor.execute(sql, (
                object_id,
                bytes(metadata['metadata_signature']),
                metadata['metadata_signature_algorithm'],
                bytes(metadata['firmware_signature']),
                metadata['firmware_signature_algorithm'],
                metadata['firmware_size'],
                metadata['release_date'],
                metadata['manufacturer_id'],
                metadata['device_type'],
                metadata['firmware_version'],
                firmware_data
            ))
        conn.commit()
        # 提交事務，確保資料寫入資料庫

# 根據廠商 ID 取得憑證（bytes 格式）
def get_manufacturer_cert(manufacturer_id):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT manufacturer_cert FROM manufacturer
                WHERE manufacturer_id = %s
                """, (manufacturer_id,))
                # 使用 %s 佔位符來避免 SQL 注入攻擊，%s會被後面的 manufacturer_id 參數替換
            result = cursor.fetchone()
            return result["manufacturer_cert"] if result else None
            # 取得查詢結果的第一筆資料，若沒有找到則回傳 None

# 找出擁有某個 manufacturer_id 的 device_type，但尚未更新為某個 firmware_version 的所有客戶
def get_customers_by_firmware(manufacturer_id, device_type, firmware_version):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            sql = """
                SELECT c.customer_id, c.bot_token, c.chatid
                FROM customer_device cd
                JOIN customer c ON cd.customer_id = c.customer_id
                WHERE cd.manufacturer_id = %s
                  AND cd.device_type = %s
                  AND cd.firmware_version != %s
            """
            # SELECT c.customer_id, c.bot_token, c.chatid: 從資料表 customer（這裡別名為 c）中，選取三個欄位
            # FROM customer_device cd：從 customer_device 資料表開始查詢，別名為 cd
            # JOIN customer c ON cd.customer_id = c.customer_id：
            # 連接 customer 表格，找出每個裝置對應的客戶資料（等於 inner join）
            # %s 會被後面的 manufacturer_id, device_type, firmware_version 參數替換
            cursor.execute(sql, (manufacturer_id, device_type, firmware_version))
            return cursor.fetchall()

# webhook 按下按鈕後，查詢 customer 的 chat_id 和 bot_token
def get_customer_chat_info(customer_id):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT customer_id, bot_token, chatid
                FROM customer
                WHERE customer_id = %s
            """, (customer_id,))
            return cursor.fetchone()

# 判斷指定 customer_id 是否存在於 customer 表
def customer_exists(customer_id):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1 FROM customer
                WHERE customer_id = %s
                LIMIT 1
                """, (customer_id,))
            return cursor.fetchone() is not None

# 查詢指定 customer 名下裝置可用的 firmware 記錄（多筆）
# JOIN customer_device / firmwaremetadata / manufacturer，
# 回傳該 customer 所屬 (manufacturer_id, device_type) 組合下的所有 firmwaremetadata，
# 並一併帶出 manufacturer_name，供 Customer Frontend 顯示。
def get_firmware_records_by_customer_id(customer_id):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            sql = """
                SELECT
                    fm.object_id,
                    fm.manufacturer_id,
                    m.manufacturer_name,
                    fm.device_type,
                    fm.firmware_version,
                    fm.firmware_size,
                    fm.release_date
                FROM customer_device cd
                JOIN firmwaremetadata fm
                  ON cd.manufacturer_id = fm.manufacturer_id
                 AND cd.device_type = fm.device_type
                JOIN manufacturer m
                  ON m.manufacturer_id = fm.manufacturer_id
                WHERE cd.customer_id = %s
                ORDER BY fm.release_date DESC
            """
            cursor.execute(sql, (customer_id,))
            return cursor.fetchall()

# 需要發送 firmware 下載請求時， 查詢該版本的 metadata 欄位放入 payload 中
# 透過 customer_id 查 customer_device 的資料表，
# 找出同樣 manufacturer + device_type 並且和 query 下來的 firmware_version 不同的所有 firmwaremetadata
def get_firmware_metadata_by_customer_id(customer_id):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            sql = """
                SELECT fm.manufacturer_id, fm.device_type, fm.firmware_version
                FROM customer_device cd
                JOIN firmwaremetadata fm
                ON cd.manufacturer_id = fm.manufacturer_id
                AND cd.device_type = fm.device_type
                WHERE cd.customer_id = %s AND cd.firmware_version != fm.firmware_version
                ORDER BY fm.release_date DESC
                LIMIT 1
            """
            cursor.execute(sql, (customer_id,))
            return cursor.fetchone()
        
# 找到特定 firmwaremetadata 並找出 firmware_data 欄位      
# 找到某個 manufacturer_id 生產的 device_type 的特定 firmware_version 的 firmwaremetadata
def save_firmware_binary(manufacturer_id, device_type, firmware_version, firmware_binary):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            sql = """
                UPDATE firmwaremetadata
                SET firmware_data = %s
                WHERE manufacturer_id = %s AND device_type = %s AND firmware_version = %s
            """
            cursor.execute(sql, (
                firmware_binary,
                manufacturer_id,
                device_type,
                firmware_version
            ))
        conn.commit()

# 查詢特定 firmwaremetadata 的 firmware_signature，用於驗證 firmware
def get_firmware_signature_metadata(manufacturer_id, device_type, firmware_version):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            sql = """
                SELECT 
                    metadata_signature_algorithm,
                    firmware_signature_algorithm,
                    firmware_signature,
                    firmware_size,
                    release_date,
                    manufacturer_id,
                    device_type,
                    firmware_version
                FROM firmwaremetadata
                WHERE manufacturer_id = %s AND device_type = %s AND firmware_version = %s
            """
            cursor.execute(sql, (manufacturer_id, device_type, firmware_version))
            row = cursor.fetchone()
            if not row:
                return None
            return dict(row)

# 查詢特定 manufacturer_id 的 manufacturer_cert
def get_manufacturer_cert(manufacturer_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT manufacturer_cert
                FROM manufacturer
                WHERE manufacturer_id = %s
            """
            cursor.execute(sql, (manufacturer_id,))
            row = cursor.fetchone()
            if row:
                return row["manufacturer_cert"]
            else:
                raise ValueError(f"找不到對應的 manufacturer_id: {manufacturer_id}")
    finally:
        conn.close()
        
# 取得特定 customer_id 名下所有裝置，並 JOIN manufacturer 以取得 manufacturer_name
def get_devices_by_customer_id(customer_id):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            sql = """
                SELECT cd.manufacturer_id,
                       m.manufacturer_name,
                       cd.device_type,
                       cd.firmware_version AS current_firmware_version,
                       cd.update_method
                FROM customer_device cd
                JOIN manufacturer m ON m.manufacturer_id = cd.manufacturer_id
                WHERE cd.customer_id = %s
                ORDER BY cd.device_type
            """
            cursor.execute(sql, (customer_id,))
            return cursor.fetchall()

# 查詢特定 customer_id 和與 query 下來 firmware_version 不同的裝置，找到 update_method、ip_address、manufacturer_id、device_type
def get_devices_by_customer_and_version(customer_id, firmware_version):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            sql = """
                SELECT cd.update_method, cd.ip_address, cd.manufacturer_id, cd.device_type
                FROM customer_device cd
                WHERE cd.customer_id = %s
                  AND cd.firmware_version != %s
            """
            cursor.execute(sql, (customer_id, firmware_version))
            return cursor.fetchall()

# 根據 firmware_version 取出 firmware_data（韌體本體）
def get_firmware_by_version(firmware_version):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            sql = """
                SELECT firmware_data
                FROM firmwaremetadata
                WHERE firmware_version = %s
            """
            cursor.execute(sql, (firmware_version,))
            result = cursor.fetchone()
            return result if result else None
       
# 查詢 firmwaremetadata 表中，特定 device_type 的所有版本
def get_latest_firmware_version_for_device(device_type):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            sql = """
                SELECT firmware_version
                FROM firmwaremetadata
                WHERE device_type = %s
                ORDER BY release_date DESC
                LIMIT 1
            """
            cursor.execute(sql, (device_type,))
            result = cursor.fetchone()
            return result["firmware_version"] if result else None

# 韌體部署成功後，更新 customer_device 資料表中的 firmware_version 欄位       
def mark_device_updated(customer_id, manufacturer_id, device_type, new_version):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE customer_device
                SET firmware_version = %s
                WHERE customer_id = %s
                  AND manufacturer_id = %s
                  AND device_type = %s
            """, (new_version, customer_id, manufacturer_id, device_type))
        conn.commit()

# 查詢特定 manufacturer_id 的製造商名稱
def get_manufacturer_name_by_id(manufacturer_id):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT manufacturer_name
                FROM manufacturer
                WHERE manufacturer_id = %s
            """, (manufacturer_id,))
            result = cursor.fetchone()
            return result["manufacturer_name"] if result else None

# 根據 mac address 更新 iot 裝置 IP 位址        
def update_device_ip_by_mac(mac, ip):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:

            sql = """
            UPDATE customer_device
            SET ip_address = %s
            WHERE mac_address = %s
            """

            cursor.execute(sql, (ip, mac))

            if cursor.rowcount == 0:
                print(f"[WARNING] Unknown device MAC: {mac}")
            
        conn.commit()

# 根據 IP 位址查詢對應 device 的 customer_id / manufacturer_id / device_type
def get_device_by_ip(ip_address):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            sql = """
                SELECT customer_id, manufacturer_id, device_type
                FROM customer_device
                WHERE ip_address = %s
                LIMIT 1
            """
            cursor.execute(sql, (ip_address,))
            return cursor.fetchone()