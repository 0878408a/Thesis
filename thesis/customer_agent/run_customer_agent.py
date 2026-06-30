import threading
import time
from webhook import app as webhook_app
from query import run_query_pipeline  
import socket
from zeroconf import Zeroconf, ServiceInfo
import socket, ssl
from werkzeug.serving import make_server

from config import (
    MANUFACTURER_CERT_PATH,
    CUSTOMER_CERT_PATH,
    CUSTOMER_KEY_PATH,
    CA_CERT_PATH
)

'''
    註冊 webhook 至 ngrok 指令:
    curl -X POST "https://api.telegram.org/<BOT_TOKEN>/setWebhook?url=/<NGROK_URL>/webhook"
    
    WSL mTLS curl 測試指令:cd /mnt/c/users/user/Downloads/ray/manufacturer_agent
    curl -v https://localhost:8000/upload_firmware/upload/   --cert ecdsa_manufacturer_client_cert.pem   --key ecdsa_manufacturer_private_key.pem   --cacert ecdsa_ca.pem
    curl -v https://localhost:8000/transfer_firmware/request_download/   --cert ecdsa_customer_public_cert.pem   --key  ecdsa_customer_private_key.pem   --cacert ecdsa_ca.pem
'''
def create_public_context():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(CUSTOMER_CERT_PATH, CUSTOMER_KEY_PATH)
    return context

def create_mtls_context():
    
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

    # server cert
    context.load_cert_chain(
        certfile=str(CUSTOMER_CERT_PATH),
        keyfile=str(CUSTOMER_KEY_PATH)
    )

    # trust CA
    context.load_verify_locations(str(CA_CERT_PATH))
    context.load_verify_locations(str(MANUFACTURER_CERT_PATH))
    
    # 要求 client cert
    context.verify_mode = ssl.CERT_REQUIRED
    
    print("Loading server cert:", CUSTOMER_CERT_PATH)
    print("Loading key:", CUSTOMER_KEY_PATH)
    print("Loading CA:", CA_CERT_PATH)
    print("Loading manufacturer cert:", MANUFACTURER_CERT_PATH)
        
    return context

# 啟動共用的 webhook 伺服器（port 5000）
def run_device_server():
    print("HTTPS server 啟動於 https://0.0.0.0:5000")
    
    # 使用 make_server 取代 Flask dev server
    httpd = make_server(
        '0.0.0.0',
        5000,
        webhook_app,
        ssl_context=create_mtls_context()
    )
    httpd.serve_forever()

def run_public_server():
    print("HTTPS server 啟動於 https://0.0.0.0:5001")
    httpd = make_server(
        '0.0.0.0',
        5001,
        webhook_app,
        ssl_context=create_public_context()
    )
    httpd.serve_forever()

# 每 3 秒對 iota 定期執行 query 任務
def run_periodic_query():
    while True:
        try:
            print("開始查詢上鏈事件紀錄...")
            run_query_pipeline()
        except Exception as e:
            print(f"[ERROR] 查詢上鏈事件紀錄時發生例外: {e}")
        time.sleep(3)  # 等待 3 秒再執行下一次

# 取得本機 LAN IP 的函式
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    s.close()
    return ip


if __name__ == "__main__":
    
    # mDNS Zeroconf 廣播，讓 esp32 可以透過 customer-agent.local:5000 來存取 customer_agent
    local_ip = get_local_ip()

    info = ServiceInfo(
    "_http._tcp.local.",
    "customer-agent._http._tcp.local.",
    addresses=[socket.inet_aton(local_ip)],
    port=5000,
    properties={},
    server="customer-agent.local."
    )

    zeroconf = Zeroconf()
    zeroconf.register_service(info)

    print(f"mDNS 服務已廣播: customer-agent.local:5000, IP={local_ip}")
    
    # 多執行緒啟動 webhook 及 query 任務
    # 將每個執行緒設為守護執行緒（daemon=True），意思是：當主程式（main thread）結束時，這個執行緒也會自動終止。
    # 這樣按 Ctrl+C 時主程式結束，子執行緒也會自動終止
    # .start() 是 Python 的 Thread 物件方法，會真正啟動這個執行緒，
    # 讓它去執行你指定的 target 函式（ run_device_server()、run_periodic_query()）。
    threading.Thread(target=run_public_server, daemon=True).start()
    threading.Thread(target=run_device_server, daemon=True).start()
    threading.Thread(target=run_periodic_query, daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("已接收到 Ctrl+C，程式即將中止。")
        zeroconf.unregister_service(info)
        zeroconf.close()
