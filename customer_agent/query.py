import requests
import json
from db import get_all_devices, firmware_exists, insert_firmware_metadata, get_manufacturer_cert
from verify import verify_signature
from telegram_notify import notify_customers

# 函式定義: def vector_u8_to_hex_string(): 將 vector<u8> 轉換為十六進位表示的字串，用於顯示 object_id
def vector_u8_to_hex_string(vector_u8):
    return "0x" + ''.join(f'{byte:02x}' for byte in vector_u8)

# 函式定義: def vector_u8_to_string(): 將 vector<u8> 轉為可讀的 UTF-8 字串
def vector_u8_to_string(vector_u8):
    """將 vector<u8> 轉換為 UTF-8 字串"""
    try:
        return bytes(vector_u8).decode('utf-8')
    except:
        return "<invalid utf-8>"

# 發送 JSON-RPC 請求查詢 FirmwareEvent 事件資料
def query_events():
    """查詢事件並回傳解析過的事件與 object_id"""
    url = "https://api.testnet.iota.cafe:443"
    payload = {
        "jsonrpc": "2.0",               # JSON-RPC 版本
        "id": 1,                        # 請求 ID ，如果同時發出多個請求（非同步），可以根據 id 判斷回應是對應哪一筆請求                             
        "method": "iotax_queryEvents",  # "method": "iotax_queryEvents" 是用於查詢事件的 JSON-RPC 方法
        "params": [                     # 查詢參數
            {   
                # package	Move Package ID（部署後的上鏈 package 位址）#######
                # module	Move 模組名稱
                # type	完整事件結構的型別（必須 fully qualified）
                
                "MoveModule": {                                 
                    "package": "0x08e70252b9d1ecd72456899d02450fd2f76cba1993b6d291d7c7094681a96933",
                    "module": "firmware_module",
                    "type": "0x08e70252b9d1ecd72456899d02450fd2f76cba1993b6d291d7c7094681a96933::firmware_module::FirmwareEvent"
                }
            },
            None,       # [1] 分頁用的 cursor(游標): None 表示從最新事件開始查詢，代表你上次查到哪。API 會從「游標之後」開始查。
                        #     optional cursor: null | EventId(string) : 
                        #     Unique ID of an IOTA Event, the ID is a combination of tx seq number and event seq number
            3,          # [2] limit: 最多 query 幾筆事件
            True        # [3] ascending: True 表示從最新往前查
        ]
    }
    headers = {
        "Content-Type": "application/json"
    }
    # 發出 POST 請求
    response = requests.post(url, headers=headers, json=payload)
    # 把 HTTP 回應的 json 物件解析成 Python dict
    data = response.json()
    
    ######
    
    # 除錯用，印出回傳資料（避免 KeyError）
    if "result" not in data:
        print("[JSON-RPC 錯誤回應]")
        print(json.dumps(data, indent=2))
        return []
    
    # 解析 JSON-RPC 回應的欄位內容
    results = [] # 建立一個空的 list，用來儲存解析後的欄位內容
    for event in data["result"]["data"]:
        '''
        迴圈從回傳結果中取出每一筆事件
        JSON-RPC 的標準回傳格式為：
        
            {
                "result": {
                    "data": [ {...}, {...}, ... ]
                }
            }
        '''
        parsed = event["parsedJson"]                            # parsedJson 是把 Move struct 解析成 JSON 的欄位
        object_id_vec = parsed["object_id"]                     # object_id 是 Move struct 的欄位，這裡是 vector<u8> 型別    
        object_id_hex = vector_u8_to_hex_string(object_id_vec)  # 將 object_id 轉換為十六進位表示的字串
        results.append({    # 將解析後的欄位內容加入 results list，每個欄位的 vector<u8> 都透過 vector_u8_to_string() 函式解碼成 UTF-8 字串 
            "object_id": object_id_hex,
            "manufacturer_id": vector_u8_to_string(parsed["manufacturer_id"]),
            "device_type": vector_u8_to_string(parsed["device_type"]),
            "firmware_version": vector_u8_to_string(parsed["firmware_version"]),
        })
    return results

def query_object_by_id(object_id_hex):
    """根據 object_id 查詢 FirmwareMetadata 並將欄位解碼"""
    url = "https://api.testnet.iota.cafe:443"
    payload = {
        "jsonrpc": "2.0",              # JSON-RPC 版本
        "id": 2,                       # 請求 ID ，如果同時發出多個請求（非同步），可以根據 id 判斷回應是對應哪一筆請求
        "method": "iota_getObject",    # 查詢物件的 JSON-RPC 方法
        "params": [
            object_id_hex,             # object_id 物件 ID，這裡是從 FirmwareEvent 中取得的 object_id
            {"showType": True, "showContent": True}
        ]   
        # "showType" 若為 True，會回傳 object 的型別（如 firmware_module::FirmwareMetadata）
        # "showContent" 若為 True，會回傳 object 的內容欄位（fields）
    }
    headers = {
        "Content-Type": "application/json"
    }
    response = requests.post(url, headers=headers, json=payload)
    # 把 HTTP 回應的 json 物件解析成 Python dict
    obj_data = response.json()

    # 防止物件查詢失敗時 KeyError
    if "result" not in obj_data or "data" not in obj_data["result"]:
        print("無法查詢到上鏈物件資料：", object_id_hex)
        print(json.dumps(obj_data, indent=2))   # 把整個回傳的 JSON 結構格式化印出（縮排為 2）
        return {}

    fields = obj_data["result"]["data"]["content"]["fields"]
    
    '''
        完整結構:
        
        {
        "result": {
            "data": {
            "content": {
                "fields": {
                    "firmware_version": [118, 49, 46, 49],
                    ...
                        }
                    }
                }
            }
        }
    '''
    decoded = {
        "firmware_version": vector_u8_to_string(fields["firmware_version"]), # vector<u8> 轉 UTF-8
        "device_type": vector_u8_to_string(fields["device_type"]),
        "manufacturer_id": vector_u8_to_string(fields["manufacturer_id"]),
        "metadata_signature_algorithm": vector_u8_to_string(fields["metadata_signature_algorithm"]),
        "firmware_signature_algorithm": vector_u8_to_string(fields["firmware_signature_algorithm"]),
        "metadata_signature": bytes(fields["metadata_signature"]), 
        "firmware_signature": bytes(fields["firmware_signature"]),
        "firmware_size": fields["firmware_size"],   
        "release_date": fields["release_date"],
    }
    return decoded

def run_query_pipeline():
    
    # 從 db 取得所有已註冊的 devices
    devices = get_all_devices()
    print(f"比對事件中...")
    all_events = query_events()  

    # 比對每個 manufacturer_id 的 device_type 是否有不存在 db 中的 firmware_version
    for device in devices:
        print(f"\n檢查裝置: {device['manufacturer_id']} / {device['device_type']}")
        
        matching_events = [
            # 從 query 下來的 all_events 中篩選出符合條件的事件
            ev for ev in all_events
            if ev["manufacturer_id"] == device["manufacturer_id"] and
               ev["device_type"] == device["device_type"] and
               not firmware_exists(ev["manufacturer_id"], ev["device_type"], ev["firmware_version"])
        ]

        if not matching_events:
            print("無新版本，略過")
            continue

        for event in matching_events:
            print(f"發現新版本: {event['firmware_version']}，查詢 metadata...")
            # 若有新版本，則透過 object_id 查詢 metadata
            metadata = query_object_by_id(event["object_id"])
            # 從 db 取得 manufacturer_cert
            cert = get_manufacturer_cert(metadata["manufacturer_id"])
            if not cert:
                print(f"找不到憑證: {metadata['manufacturer_id']}")
                continue
            
            # print(f"[DEBUG] metadata_signature type = {type(metadata['metadata_signature'])}")
            # print(f"[DEBUG] metadata_signature = {metadata['metadata_signature'][:30]}...")

            # 呼叫 verify_signature() 驗證 metadata 的簽章
            if verify_signature(metadata, cert, "metadata_signature", metadata["metadata_signature"]):
                insert_firmware_metadata(event["object_id"], metadata)
                print(f"成功寫入 DB: {metadata['firmware_version']}")
                
                # 呼叫 Telegram 通知
                notify_customers(metadata)
                
            else:
                print(f"驗章失敗:韌體版本 {metadata['firmware_version']}")

# 主流程
if __name__ == "__main__":
    
    # 從 db 取得所有已註冊的 devices
    devices = get_all_devices()
    print(f"查詢全部事件中...")
    all_events = query_events()  

    # 比對每個 manufacturer_id 的 device_type 是否有不存在 db 中的 firmware_version
    for device in devices:
        print(f"\n檢查裝置: {device['manufacturer_id']} / {device['device_type']}")
        
        matching_events = [
            # 從 query 下來的 all_events 中篩選出符合條件的事件
            ev for ev in all_events
            if ev["manufacturer_id"] == device["manufacturer_id"] and
               ev["device_type"] == device["device_type"] and
               not firmware_exists(ev["manufacturer_id"], ev["device_type"], ev["firmware_version"])
        ]

        if not matching_events:
            print("無新版本，略過")
            continue

        for event in matching_events:
            print(f"發現新版本: {event['firmware_version']}，查詢 metadata...")
            # 若有新版本，則透過 object_id 查詢 metadata
            metadata = query_object_by_id(event["object_id"])
            # 從 db 取得 manufacturer_cert
            cert = get_manufacturer_cert(metadata["manufacturer_id"])
            if not cert:
                print(f"找不到憑證: {metadata['manufacturer_id']}")
                continue
            
            # print(f"[DEBUG] metadata_signature type = {type(metadata['metadata_signature'])}")
            # print(f"[DEBUG] metadata_signature = {metadata['metadata_signature'][:30]}...")

            # 呼叫 verify_signature() 驗證 metadata 的簽章
            if verify_signature(metadata, cert, "metadata_signature", metadata["metadata_signature"]):
                insert_firmware_metadata(event["object_id"], metadata)
                print(f"成功寫入 DB: {metadata['firmware_version']}")
                
                # 呼叫 Telegram 通知
                notify_customers(metadata)
                
            else:
                print(f"驗章失敗:韌體版本 {metadata['firmware_version']}")

                
                
    #### debug 用：查詢事件，顯示 object_id，查詢對應 FirmwareMetadata 物件 ####

    event_results = query_events()
    for event in event_results:
        print(f"\n Firmware Event:")
        print(f"- Object ID: {event['object_id']}")
        print(f"- Manufacturer ID: {event['manufacturer_id']}")
        print(f"- Device Type: {event['device_type']}")
        print(f"- Firmware Version: {event['firmware_version']}")
        print(f"")
        print("查詢鏈上 FirmwareMetadata 資料：")
        # 使用 object_id 再鏈上查詢 FirmwareMetadata 物件
        metadata = query_object_by_id(event["object_id"])
        # 走訪 metadata 字典的每一個鍵值對
        # k 是欄位名稱（如 "firmware_version"），v 是對應的值（如 "v1.1"）
        for k, v in metadata.items():
            print(f"  {k}: {v}")