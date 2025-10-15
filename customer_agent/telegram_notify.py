import requests
import json
from db import get_customers_by_firmware, get_manufacturer_name_by_id  
from datetime import datetime, timedelta, timezone
import zoneinfo

def send_telegram_message(bot_token, chat_id, message, customer_id=None, firmware_version=None, parse_mode=None):
    """
    使用指定的 Telegram Bot Token 傳送訊息到 chat_id
    """
    # bot_token: Telegram 分配給某個 Bot 的唯一身份憑證
    # chat_id: Telegram 聊天室 ID，可以是個人或群組的 ID
    # message: 要傳送的訊息內容
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }
    # 如果有指定按鈕資訊，加入 inline keyboard
    if customer_id and firmware_version:
        payload["reply_markup"] = json.dumps({
            "inline_keyboard": [[
                {
                    "text": f"下載並部署韌體版本: {firmware_version}",
                    "callback_data": f"install_fw:{customer_id}:{firmware_version}"
                }
            ]]
        })

    #print("[DEBUG] payload =")
    #print(json.dumps(payload, indent=2))
    
    response = requests.post(url, data=payload)
    
    #print("[DEBUG] status =", response.status_code)
    #print("[DEBUG] response =", response.text)
    
    if response.status_code == 200:
        print(f"成功通知 chat_id={chat_id}")
    else:
        print(f"傳送失敗 chat_id={chat_id}：{response.text}")

def notify_customers(metadata):
    """
    傳送 metadata 通知韌體更新給所有符合的 customer
    """
    metadata_signature_algorithm = metadata["metadata_signature_algorithm"]
    metadata_signature = metadata["metadata_signature"]
    manufacturer_id = metadata["manufacturer_id"]
    device_type = metadata["device_type"]
    firmware_version = metadata["firmware_version"]

    # 取得 manufacturer_name
    manufacturer_name = get_manufacturer_name_by_id(manufacturer_id)
    if not manufacturer_name:
        print(f"找不到對應的 manufacturer_name: {manufacturer_id}")
        manufacturer_name = f"(未知製造商 {manufacturer_id})"
    
    # 查詢使用此裝置，但目前 firmware_version 不是最新版本的所有客戶的資料，如下:
    '''
        {
            "customer_id": "abc-123",
            "bot_token": "123456:ABC-DEF...",
            "chatid": "987654321"
        }
    '''
    customers = get_customers_by_firmware(manufacturer_id, device_type, firmware_version)
    if not customers:
        print(" 無對應客戶可通知")
        return

    # NTP timestamp 轉換為 datetime（NTP epoch 是 1900-01-01）
    def ntp_to_datetime(ntp_timestamp):
        ntp_epoch = datetime(1900, 1, 1, tzinfo=timezone.utc)
        utc_time = ntp_epoch + timedelta(seconds=int(ntp_timestamp))
        return utc_time.astimezone(zoneinfo.ZoneInfo("Asia/Taipei"))
        
    message = (
        f" 韌體更新通知\n\n"
        # f" 韌體 metadata 簽章演算法: {metadata_signature_algorithm}\n"
        # f" 韌體 metadata 簽章: \n{metadata_signature.hex()}\n"
        f" 裝置型號: {device_type}\n"
        f" 製造商:   {manufacturer_name}\n"
        f" 韌體版本: {firmware_version}\n"
        f" 發佈時間: {ntp_to_datetime(metadata['release_date']).strftime('%Y-%m-%d %H:%M:%S')}\n"
        f" 大小: {metadata['firmware_size']} bytes"
    )###### 改成客戶看得懂的版本
    # 對每一個符合條件的 customer：
    # 呼叫 send_telegram_message() 傳送通知，並傳入 bot_token、chat_id 和訊息內容
    for customer in customers:
        send_telegram_message(
            bot_token=customer["bot_token"],
            chat_id=customer["chatid"],
            message=message,
            customer_id=customer["customer_id"],             
            firmware_version=firmware_version
        )


# 測試用

if __name__ == "__main__":
    dummy_metadata = {
        "manufacturer_id": "123e4567-e89b-12d3-a456-426614174000",
        "device_type": "esp32",
        "firmware_version": "v1.1",
        "release_date": "3854745600",
        "firmware_size": 1024000
    }
    notify_customers(dummy_metadata)
