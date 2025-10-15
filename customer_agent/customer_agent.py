import threading
import time
import ssl
import os
from webhook import app as webhook_app
from query import run_query_pipeline  
from pathlib import Path

# 憑證與私鑰路徑
CUSTOMER_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_customer_public_cert.pem")
CUSTOMER_KEY_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/ecdsa_customer_private_key.pem")
# DEVICE_CERT_PATH = Path("C:/Users/User/Downloads/ray/manufacturer_agent/esp32_device_cert.pem")

UPLOAD_FOLDER = "firmware_uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

'''
    註冊 webhook 至 ngrok 指令:
    curl -X POST "https://api.telegram.org/botREMOVED/setWebhook?url=https://你的-ngrok-url/webhook"
    
    WSL mTLS curl 測試指令:cd /mnt/c/users/user/Downloads/ray/manufacturer_agent
    curl -v https://localhost:8000/upload_firmware/upload/   --cert ecdsa_manufacturer_public_cert.pem   --key ecdsa_manufacturer_private_key.pem   --cacert ecdsa_ca.pem
    curl -v https://localhost:8000/transfer_firmware/request_download/   --cert ecdsa_customer_public_cert.pem   --key  ecdsa_customer_private_key.pem   --cacert ecdsa_ca.pem
'''

@webhook_app.route("/update", methods=["POST"])
# 啟動共用的 webhook 伺服器（port 5000）
def run_http_server():
    print("HTTP server 啟動於 http://0.0.0.0:5000")
    '''
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(certfile=CUSTOMER_CERT_PATH, keyfile=CUSTOMER_KEY_PATH)
    context.load_verify_locations(cafile=str(CUSTOMER_CERT_PATH))
    context.verify_mode = ssl.CERT_REQUIRED
    # context.check_hostname = False
    '''
    # webhook_app.run(host="0.0.0.0", port=5000, ssl_context=context)
    webhook_app.run(host="0.0.0.0", port=5000)

# 每 3 秒對 iota 定期執行 query 任務
def run_periodic_query():
    while True:
        try:
            print("開始查詢上鏈事件紀錄...")
            run_query_pipeline()
        except Exception as e:
            print(f"[ERROR] 查詢上鏈事件紀錄時發生例外: {e}")
        time.sleep(3)  # 等待 3 秒再執行下一次

if __name__ == "__main__":
    # 多執行緒啟動 webhook 及 query 任務
    # 將每個執行緒設為守護執行緒（daemon=True），意思是：當主程式（main thread）結束時，這個執行緒也會自動終止。
    # 這樣按 Ctrl+C 時主程式結束，子執行緒也會自動終止
    # .start() 是 Python 的 Thread 物件方法，會真正啟動這個執行緒，
    # 讓它去執行你指定的 target 函式（ run_http_server()、run_periodic_query()）。
    threading.Thread(target=run_http_server, daemon=True).start()
    threading.Thread(target=run_periodic_query, daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("已接收到 Ctrl+C，程式即將中止。")
