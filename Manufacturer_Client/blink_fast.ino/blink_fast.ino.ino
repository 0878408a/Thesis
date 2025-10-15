#include <WiFi.h>
#include <WebServer.h>
#include <Update.h>

const char* ssid = "Redmi K20 Pro";
const char* password = "19981120";

// 建立 HTTP 伺服器，監聽 port 80
WebServer server(80);

// 處理韌體的接收與寫入
void handleFirmwareUpload() {
  
  // upload 是 ESP32 接收表單檔案上傳的物件，會根據上傳狀態有:上傳、寫入、結束三個階段
  HTTPUpload& upload = server.upload();
  
  // 1. UPLOAD_FILE_START：檔案開始上傳
  if (upload.status == UPLOAD_FILE_START) {
    Serial.printf("開始 OTA 韌體更新: %s\n", upload.filename.c_str());

    // 呼叫 Update.begin() 準備寫入 Flash（會嘗試使用最大空間）
    if (!Update.begin()) { // 使用最大空間
      Update.printError(Serial);
    }
    
  // 2. UPLOAD_FILE_WRITE：正在寫入資料
  } else if (upload.status == UPLOAD_FILE_WRITE) {
    // 寫入韌體，將 upload.buf 中的資料寫入 Flash
    if (Update.write(upload.buf, upload.currentSize) != upload.currentSize) {
      Update.printError(Serial);
    }
    
  // 3. UPLOAD_FILE_END：上傳結束
  } else if (upload.status == UPLOAD_FILE_END) {
    if (Update.end(true)) {
      Serial.println("韌體更新完成，將重新啟動...");
      server.send(200, "text/plain", "Firmware update successful. Rebooting...");
      delay(1000);
      ESP.restart();
    } else {
      Update.printError(Serial);
      server.send(500, "text/plain", "Update failed");
    }
  }
}

void setup() {
    // 開始連線 WiFi 並等候成功
  Serial.begin(115200);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) delay(100);

  Serial.println("ESP32 已連線");
  Serial.print("IP 地址：");
  Serial.println(WiFi.localIP());
  
  server.on("/update", HTTP_POST, []() {
    // 設定 /update 的 POST 路由
    // handleFirmwareUpload 是檔案上傳的處理函式
  }, handleFirmwareUpload);

  server.begin();
  // 啟動 HTTP Server
  Serial.println("準備接收韌體更新...");

  pinMode(LED_BUILTIN, OUTPUT);
}

// loop 函式會不斷重複執行
void loop() {
  digitalWrite(LED_BUILTIN, HIGH);  // 亮
  delay(200);
  digitalWrite(LED_BUILTIN, LOW);   // 滅
  delay(200);

  // 持續處理用戶端的 HTTP 請求（如上傳韌體）
  server.handleClient();
}
