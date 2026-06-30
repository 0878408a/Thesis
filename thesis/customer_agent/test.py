import socket
import ssl
from zeroconf import Zeroconf, ServiceInfo
from http.server import HTTPServer, BaseHTTPRequestHandler

from config import (
    CUSTOMER_CERT_PATH,
    CUSTOMER_KEY_PATH,
    CA_CERT_PATH,
)

HOST = "0.0.0.0"
PORT = 5000


def create_ssl_context():
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

    # server cert (customer agent)
    context.load_cert_chain(
        certfile=str(CUSTOMER_CERT_PATH),
        keyfile=str(CUSTOMER_KEY_PATH)
    )

    # trust CA (root CA)
    context.load_verify_locations(str(CA_CERT_PATH))
    
    # 強制 client 要帶 cert
    context.verify_mode = ssl.CERT_REQUIRED

    print("Loading server cert:", CUSTOMER_CERT_PATH)
    print("Loading key:", CUSTOMER_KEY_PATH)
    print("Loading CA:", CA_CERT_PATH)

    return context


# 最簡單 HTTP handler
class TestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        print("收到 GET request from:", self.client_address)

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"mTLS OK\n")


# 取得 LAN IP
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    s.close()
    return ip


if __name__ == "__main__":

    # ===== mDNS 廣播 =====
    local_ip = get_local_ip()

    info = ServiceInfo(
        "_http._tcp.local.",
        "customer-agent._http._tcp.local.",
        addresses=[socket.inet_aton(local_ip)],
        port=PORT,
        properties={},
        server="customer-agent.local."
    )

    zeroconf = Zeroconf()
    zeroconf.register_service(info)

    print(f"mDNS 已啟動: https://customer-agent.local:{PORT} -> {local_ip}")

    # ===== HTTPS Server =====
    httpd = HTTPServer((HOST, PORT), TestHandler)
    ssl_context = create_ssl_context()

    httpd.socket = ssl_context.wrap_socket(
        httpd.socket,
        server_side=True
    )

    print("HTTPS mTLS server 啟動成功")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("關閉中...")
        zeroconf.unregister_service(info)
        zeroconf.close()
        httpd.server_close()