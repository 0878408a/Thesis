from guizero import App, Text, TextBox, PushButton, info, error
from tkinter import Tk
from tkinter.filedialog import askopenfilename
# 用於顯示文件選擇對話框，讓用戶選擇文件。
import requests
# 用於發送 HTTP 請求

# Django API URL
SUBMIT_BLOCK_URL = "http://127.0.0.1:8000/submit_block/submit/"

# 選擇json文件功能
def select_data_file():
    Tk().withdraw()  # 隱藏 Tkinter 主窗口
    file_path = askopenfilename(title="Select Data File", filetypes=[("JSON files", "*.json")])
    if file_path:
        data_file_input.value = file_path # 輸入檔案路徑

# 提交區塊功能
def submit_block():
    tag = tag_input.value
    data_file_path = data_file_input.value

        # 讀取數據文件內容
    with open(data_file_path, 'r') as file:
            data = file.read()
        # with 是 Python 中的 Context Manager，能保證文件在程式執行結束後自動關閉。
        # 'r'：文件打開模式，表示以唯讀模式打開文件
        # file.read(): 讀取文件的全部內容，並將其作為字串返回。
        
    if not data.strip():
    # 判斷去除空白字符後的 data 是否為空字串。
            error("Error", "Data file is empty!")
            return

    # 發送 POST 請求到後端 API
    response = requests.post(SUBMIT_BLOCK_URL, json={'tag': tag, 'data': data})
    print("Raw Response Content:", response.text)  # 輸出原始回應內容
    
    try:
        result = response.json() # 將 HTTP 回應的內容轉換為 JSON 格式的 Python 字典
        if response.status_code == 201:
                info("Success", f"Block Submitted! Block ID: {result['block_id']}")
        else:
                error("Error", f"Failed to submit block: {result.get('error', 'Unknown error')}")
    except ValueError: # ValueError 表示一個函數或操作接收到具有正確類型但值不正確的參數
            error("Error", "Invalid response from server. Please check the backend.")
    except Exception as e: # Exception 是 Python 所有內建異常的 Base class
        error("Error", f"An exception occurred: {str(e)}")

# 建立 GUI
app = App(title="Manufacturer Client", width=600, height=400)

# 標題
Text(app, text="Manufacturer User 管理系統", size=16, color="blue")

# Tag 輸入(Customer UUID)
Text(app, text="輸入Customer UUID:")
tag_input = TextBox(app, width=50)

# 文件選擇
Text(app, text="Select Data File:")
data_file_input = TextBox(app, width=50)
PushButton(app, text="Choose FirmwareMetadata File", command=select_data_file)

# 提交按鈕
PushButton(app, text="Submit Block", command=submit_block)

# 啟動 GUI
app.display()
