#include <WiFi.h>
#include <WebServer.h>
#include <Update.h>

/*
  Update.h 是 ESP32 Arduino 核心內建的 OTA 韌體更新函式庫，提供底層 API 讓你能夠將新的韌體寫入 Flash，常見用法就是：
  
  HTTP Server OTA:
    
    ESP32 自己開伺服器（如程式用 WebServer server(80)），你從 PC 端或伺服器對 ESP32 發出 POST 韌體更新請求。
  
  HTTP Client OTA:
    
    ESP32 自己當作「客戶端」，去伺服器拉 .bin 韌體來更新。
  
  使用 SPIFFS 或 SD 卡中的 .bin 檔更新  
*/
const char* ssid = "Redmi K20 Pro";
const char* password = "19981120";

// 建立 HTTP 伺服器，監聽 port 80
WebServer server(80);

// 處理韌體的接收與寫入
void handleFirmwareUpload() {
  
  // upload 是 ESP32 接收表單檔案上傳的物件，會根據上傳狀態有:上傳、寫入、結束三個階段
  HTTPUpload& upload = server.upload();
  
  // 1. UPLOAD_FILE_START：檔案開始上傳
  // upload.status 表示的是目前正在處理的上傳階段，這是 ESP32WebServer 的內建上傳機制之一，upload.status 會依據進度自動變動。
  if (upload.status == UPLOAD_FILE_START) {
    Serial.printf("開始 OTA 韌體更新: %s\n", upload.filename.c_str());

    // 呼叫 Update.begin() 準備寫入 Flash（預設嘗試使用最大可用空間）
    if (!Update.begin()) { // 使用最大空間
      Update.printError(Serial);
    }
    
  // 2. UPLOAD_FILE_WRITE：正在寫入資料
  } else if (upload.status == UPLOAD_FILE_WRITE) {
    // 寫入韌體，將 upload.buf 中的資料寫入 Flash
    // Update.write(buf, len): buf：目前收到的一段韌體資料，len：這段資料的長度
    if (Update.write(upload.buf, upload.currentSize) != upload.currentSize) {
      Update.printError(Serial);
    }
    
  // 3. UPLOAD_FILE_END：上傳結束
  } else if (upload.status == UPLOAD_FILE_END) {
    // Update.end([bool evenIfIncomplete])
    // 結束寫入並檢查更新是否成功
    // true：即使寫入不完整也強制結束
    // false：會檢查實際寫入長度與 begin() 給的大小是否相符
    if (Update.end(true)) {
      Serial.println("韌體更新完成，將重新啟動...");
      server.send(200, "text/plain", "Firmware update successful. Rebooting...");
      delay(1000);
      // 更新成功後重新啟動裝置，並從新韌體開機。
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
  // server.on(path, method, handlerFunction, uploadFunction);
  // path const char* 要處理的 URL 路徑，例如 "/update"
  // method  HTTPMethod  HTTP 方法（如 HTTP_GET、HTTP_POST）
  // handlerFunction std::function<void()>（可用 lambda）處理「不含上傳檔案」的http請求（例如純 JSON、HTML 表單等）這裡用了[](){}表示不用(不可省略)
  // uploadFunction  THandlerFunction 專門處理檔案上傳事件（如 OTA 韌體）這裡傳了 handleFirmwareUpload
  server.on("/update", HTTP_POST, []() {
    // 設定 /update 的 POST 路由
    // handleFirmwareUpload 是檔案上傳的處理函式
  }, handleFirmwareUpload);

  server.begin();
  // 啟動 HTTP Server
  Serial.println("準備接收韌體更新...");
}

void loop() {
  // 持續處理用戶端的 HTTP 請求（如上傳韌體）
  server.handleClient();
}
