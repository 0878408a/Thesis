from flask import Flask, request, jsonify, Response
import subprocess
import sys
import traceback
import requests
from db import get_customer_chat_info, mark_device_updated, get_firmware_by_version, update_device_ip_by_mac, get_device_by_ip  
from telegram_notify import send_telegram_message
import config

# Telegram Webhook Flask App
app = Flask(__name__)

# 讓 webhook 或 subprocess 中的程式（如 customer_request.py）使用的 Customer Agent API URL
AGENT_URL = "http://localhost:8080/api/download"

# 將 Telegram callback 中的 data 欄位解析為格式 install_fw:<customer_id>:<firmware_version>。
# 如果資料格式錯誤，回傳 (None, None)。
def parse_callback_data(data):
    try:
        if data.startswith("install_fw:"):
            # 去除前綴 "install_fw:"，並分割剩餘部分
            _, customer_id, firmware_version = data.split(":")
            return customer_id, firmware_version
    except ValueError:
        pass
    return None, None

# Device Register API 用於更新db內的 iot 裝置的 ip 位址
@app.route("/register_device", methods=["POST"])
def register_device():
    try:
        
        data = request.get_json()
        
        print("[DEBUG] Received payload:", data)
        
        mac = data.get("mac_address") 
        
        if not mac:
            return jsonify({"error": "missing mac_address"}), 400

        mac = mac.lower()

        # 取得 ESP32 IP
        device_ip = request.remote_addr

        # 更新 DB
        update_device_ip_by_mac(mac, device_ip)

        print(f"[Device Register] {mac} -> {device_ip}")

        return jsonify({"status": "ok"})

    except Exception as e:
        print("[Register Error]", e)
        return jsonify({"error": "register failed"}), 500

@app.route("/report_update", methods=["POST"])
def report_update():
    try:
        data = request.get_json()
        print("[DEBUG] OTA report:", data)

        version = data.get("version")

        if not version:
            return jsonify({"error": "missing version"}), 400

        # 用 IP 找 device
        device_ip = request.remote_addr
        device = get_device_by_ip(device_ip)

        if not device:
            return jsonify({"error": "device not found"}), 404

        mark_device_updated(
            device["customer_id"],
            device["manufacturer_id"],
            device["device_type"],
            version
        )

        print(f"[OTA 完成] {device['device_type']} -> {version}")

        return jsonify({"status": "ok"})

    except Exception as e:
        print("[report_update error]", e)
        return jsonify({"error": "failed"}), 500

@app.route("/download_firmware", methods=["GET"])
def download_firmware():
    version = request.args.get("version")
    
    fw = get_firmware_by_version(version)

    if not fw:
        return "not found", 404

    return Response(
        fw["firmware_data"],
        mimetype="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=fw_{version}.bin"
        }
    )

# 查詢資料庫中符合 customer_id 的 user。
# 回傳第一筆符合的 bot_token、chat_id 資訊。
def get_chat_info_by_customer(customer_id):
    result = get_customer_chat_info(customer_id)
    return result if result else None

# 使用 subprocess 呼叫 customer_request.py
# 將 customer_id 和 firmware_version 傳給 customer_request.py
CUSTOMER_REQUEST_PATH = config.CUSTOMER_REQUEST_PATH
APPLY_PATH = config.APPLY_PATH

# 觸發韌體下載並部署的函式。
# 這個函式會呼叫 customer_request.py，並傳入 customer_id 和 firmware_version。
# 如果下載成功，會自動呼叫 apply.py 進行韌體部署。
def trigger_download_and_apply(customer_id, firmware_version):
    try:
        
        TRANSFER_FW_DIR = config.CUSTOMER_AGENT_DIR
        # 沒有 cwd 指定 customer_request.py 的執行目錄，而該程式會嘗試載入憑證與憑證路徑，因此會找不到檔案或印不出訊息
        result = subprocess.run(
            [sys.executable, str(CUSTOMER_REQUEST_PATH), customer_id, firmware_version],
            # 使用 stdout 和 stderr 捕捉輸出
            # subprocess.PIPE: 把子行程的 標準輸出（如 print 或 printf）透過管線（pipe）回傳給父行程，
            # 而不是直接印在終端機上
            # text=True: 讓 stdout 和 stderr 的輸出為文字格式（字串），而不是 bytes
            # check=True: 如果子行程返回非零狀態碼，則引發 CalledProcessError
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            cwd=TRANSFER_FW_DIR,  # 確保從正確目錄執行
        )

        # 清理 stdout 回傳內容（去除多餘換行）
        stdout_clean = result.stdout.strip()

        # 加上除錯輸出
        print("[DEBUG] customer_request.py stdout:")
        print(result.stdout)
        print("[DEBUG] customer_request.py stderr:")
        print(result.stderr)

        # 下載成功後呼叫 apply.py 自動部署
        apply_result = subprocess.run(
            [sys.executable, str(APPLY_PATH), customer_id, firmware_version],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            cwd=TRANSFER_FW_DIR,  # 指定執行目錄
        )

        apply_stdout = apply_result.stdout.strip()
        print("[DEBUG] apply.py output:")
        print(apply_stdout)

        return 200, f"韌體安裝完成\n{apply_stdout}"

    except subprocess.CalledProcessError as e:
        stderr_clean = e.stderr.strip()
        print("[ERROR] subprocess error:")
        print(stderr_clean)
        return 500, stderr_clean or "執行失敗但無錯誤輸出"

# 錯誤處理器：印出錯誤到主控台，並傳送錯誤訊息給 Telegram 使用者。
def handle_error(bot_token, chat_id, msg, error=None):
    if error:
        print(f"[Webhook Error] {msg}: {error}")
        traceback.print_exc()
    else:
        print(f"[Webhook Error] {msg}")
    if bot_token and chat_id:
        send_telegram_message(bot_token, chat_id, f" {msg}")

@app.route("/webhook", methods=["POST"])
# Telegram Bot Server 會透過 POST 請求呼叫這個 webhook（已用 ngrok 註冊該 webhook）
# ngrok 是一個簡易的 reverse proxy 工具，且自帶 https 憑證
def telegram_webhook():
    # 取得 Telegram 發送的 JSON payload
    update = request.get_json()

    # 判斷是否為按鈕點擊（Telegram 會用 callback_query）。
    # 解析出 customer_id 與 firmware_version。
    if "callback_query" in update:
        callback = update["callback_query"]
        data = callback.get("data", "")
        # 呼叫函式 parse_callback_data(data)，並將它回傳的結果分別存入 customer_id 和 firmware_version 兩個變數中
        customer_id, firmware_version = parse_callback_data(data)

        if not customer_id or not firmware_version:
            return jsonify({"ok": False, "error": "callback_data 格式錯誤"}), 400

        bot_token = None
        chat_id = None

        try:
            # 根據 customer_id 查詢資料庫，取得對應的 Telegram 使用者資訊
            # 這個函式會回傳一個 tuple，包含 bot_token 和 chatid
            chat_info = get_chat_info_by_customer(customer_id)
            if not chat_info:
                return jsonify({"ok": False, "error": "找不到對應用戶"}), 404

            # 收到 Telegram 使用者按下 inline button 的 callback event 後，
            # 從資料庫查出對應的使用者資訊，並呼叫 trigger_download_and_apply 發送韌體下載請求給 manufacturer agent
            chat_id = chat_info["chatid"]
            bot_token = chat_info["bot_token"]

            # 傳入 customer_id 和 firmware_version 參數，觸發韌體下載和部署，回傳 status_code 和 response_text
            status_code, response_text = trigger_download_and_apply(customer_id, firmware_version)

            if status_code == 200:
                # 成功安裝韌體後，發送通知給 Telegram 使用者
                send_telegram_message(bot_token, chat_id, response_text)
            else:
                handle_error(bot_token, chat_id, f"安裝請求失敗：{status_code} - {response_text}")


        except Exception as e:
            handle_error(bot_token, chat_id, "webhook 發生例外錯誤", e)
            return jsonify({"ok": False, "error": "webhook 發生例外錯誤"}), 500

    return jsonify({"ok": True})

# 啟動 HTTPS Webhook 
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
