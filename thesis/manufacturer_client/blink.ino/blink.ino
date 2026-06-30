#include <WiFi.h>
#include <WebServer.h>
#include <Update.h>
#include <HTTPClient.h>
#include <WiFiManager.h> 
#include <ESPmDNS.h>
#include <WiFiClientSecure.h>
#include "esp32-hal-log.h"
#include <time.h>
#include <ArduinoJson.h>

/*
 Root CA certificate
*/
static const char root_ca[] PROGMEM = R"KEY(
-----BEGIN CERTIFICATE-----
MIICSDCCAe6gAwIBAgIUXW0ZJgFkuVcWEKt/sIF9lZF+vmgwCgYIKoZIzj0EAwIw
ZTELMAkGA1UEBhMCVFcxDzANBgNVBAgMBlRhaXdhbjESMBAGA1UEBwwJS2FvaHNp
dW5nMQwwCgYDVQQKDANJU1UxDTALBgNVBAsMBENTSUUxFDASBgNVBAMMC0lTVV9S
b290X0NBMB4XDTI1MDYyMzEyMjgyOVoXDTM1MDYyMTEyMjgyOVowZTELMAkGA1UE
BhMCVFcxDzANBgNVBAgMBlRhaXdhbjESMBAGA1UEBwwJS2FvaHNpdW5nMQwwCgYD
VQQKDANJU1UxDTALBgNVBAsMBENTSUUxFDASBgNVBAMMC0lTVV9Sb290X0NBMFkw
EwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAENZtdGZTYix21UAyLMdnNpqktTxxprXOn
rNq8m2MQSIvIBSGgEWv2AQaCLW/hWwP8BfSNKjs3OgLRt1v1wgBEKqN8MHowDAYD
VR0TBAUwAwEB/zAdBgNVHQ4EFgQUAR0xNtW7tnGFu6wLKkt4UFJ0wLQwCwYDVR0P
BAQDAgGmMB0GA1UdJQQWMBQGCCsGAQUFBwMBBggrBgEFBQcDAjAfBgNVHSMEGDAW
gBQBHTE21bu2cYW7rAsqS3hQUnTAtDAKBggqhkjOPQQDAgNIADBFAiEAj7ZL+geM
4hqAsLBSUhwTAGnXzkVT1QS2hOpxBtcomTACIA7O3MRuM42tUco1BX5cZmEfkcNn
TfppUcs3OVfqvD6J
-----END CERTIFICATE-----
)KEY";

static const char device_cert[] PROGMEM = R"KEY(
-----BEGIN CERTIFICATE-----
MIIC2zCCAoCgAwIBAgIUdA3eO9m0HY5KnChLRpNuPn3/b0QwCgYIKoZIzj0EAwIw
gaoxCzAJBgNVBAYTAlRXMRIwEAYDVQQIDAlLYW9oc2l1bmcxEjAQBgNVBAcMCUth
b2hzaXVuZzEMMAoGA1UECgwDSVNVMRkwFwYDVQQLDBBDU0lFX05FVFdPUktfTEFC
MSEwHwYDVQQDDBhtYW51ZmFjdHVyZXIuZXhhbXBsZS5jb20xJzAlBgkqhkiG9w0B
CQEWGG1hbnVmYWN0dXJlckBleGFtcGxlLmNvbTAeFw0yNjAzMjQxNDIwMjlaFw0z
NjAzMjExNDIwMjlaMIGcMQswCQYDVQQGEwJUVzESMBAGA1UECAwJS2FvaHNpdW5n
MRIwEAYDVQQHDAlLYW9oc2l1bmcxFTATBgNVBAoMDE1hbnVmYWN0dXJlcjEPMA0G
A1UECwwGQ2xpZW50MRswGQYDVQQDDBJlc3AzMi1lODY4ZTcyMzcxZDgxIDAeBgkq
hkiG9w0BCQEWEWVzcDMyLmV4YW1wbGUuY29tMFkwEwYHKoZIzj0CAQYIKoZIzj0D
AQcDQgAEn4SsqHKin9r3zLNxYRAsS0AwvEroJ/aLro5qgflSVV4sm2QPZOKd12ZS
J8xxarZ2ER42+Ozl08BtcBtJUKZhRqOBjzCBjDAJBgNVHRMEAjAAMAsGA1UdDwQE
AwIFoDATBgNVHSUEDDAKBggrBgEFBQcDAjAdBgNVHREEFjAUghJlc3AzMi1lODY4
ZTcyMzcxZDgwHQYDVR0OBBYEFMBEhZjxqPuUXrxzc2e1eTq9Ac6ZMB8GA1UdIwQY
MBaAFAW4ZTj1P3W4sTuH1UK5DpbgTNPLMAoGCCqGSM49BAMCA0kAMEYCIQCRJ3bM
aEoopcdCmZ0T9L86JV3FqJb2onUPAoxqoqweWQIhANOoa60pOR+wsO1d9luzDmRg
IghMkVRzDkwIomwtbrF3
-----END CERTIFICATE-----
)KEY";

static const char device_key[] PROGMEM = R"KEY(
-----BEGIN EC PRIVATE KEY-----
MHcCAQEEIMgBDdzithZLDFzf/IYA/wJvLEaEDuaMJMMWQISMYvpGoAoGCCqGSM49
AwEHoUQDQgAEn4SsqHKin9r3zLNxYRAsS0AwvEroJ/aLro5qgflSVV4sm2QPZOKd
12ZSJ8xxarZ2ER42+Ozl08BtcBtJUKZhRg==
-----END EC PRIVATE KEY-----
)KEY";

/*
  Update.h 是 ESP32 Arduino 核心內建的 OTA 韌體更新函式庫，提供底層 API 讓你能夠將新的韌體寫入 Flash，常見用法就是：
  
  HTTP Server OTA:
    
    ESP32 自己開伺服器（如程式用 WebServer server(80)），你從 PC 端或伺服器對 ESP32 發出 POST 韌體更新請求。
  
  HTTP Client OTA:
    
    ESP32 自己當作「客戶端」，去伺服器拉 .bin 韌體來更新。
  
  使用 SPIFFS 或 SD 卡中的 .bin 檔更新  
*/

WebServer server(80);
String pendingVersion = "";
bool shouldUpdate = false;

void handleTriggerUpdate() {
  String body = server.arg("plain");

  Serial.println("收到更新通知:");
  Serial.println(body);

  JsonDocument doc;

  DeserializationError error = deserializeJson(doc, body);

  if (error) {
    Serial.print("JSON parse failed: ");
    Serial.println(error.c_str());
    server.send(400, "text/plain", "invalid json");
    return;
  }

  // 取 version
  if (!doc["version"].is<String>()) {
    server.send(400, "text/plain", "missing version");
    return;
  }

  String version = doc["version"].as<String>();
  pendingVersion = version;
  shouldUpdate = true;

  Serial.print("目標版本: ");
  Serial.println(pendingVersion);

  server.send(200, "text/plain", "ok");
}

void performOTA(String version) {

  WiFiClientSecure client;
  client.setCACert(root_ca);
  client.setCertificate(device_cert);
  client.setPrivateKey(device_key);

  HTTPClient https;

  String url = "https://customer-agent.local:5000/download_firmware?version=" + version;

  Serial.println("開始下載 OTA...");
  Serial.println(url);

  if (!https.begin(client, url)) {
    Serial.println("HTTPS begin failed");
    return;
  }

  int httpCode = https.GET();

  if (httpCode != 200) {
    Serial.printf("HTTP GET failed: %d\n", httpCode);
    https.end();
    return;
  }

  int contentLength = https.getSize();
  WiFiClient *stream = https.getStreamPtr();

  if (contentLength <= 0) {
  Serial.println("Invalid content length");
  https.end();
  return;
  }

  if (!Update.begin(contentLength, U_FLASH)) {
  Update.printError(Serial);
  https.end();
  return;
  }

  Serial.println("開始寫入 firmware...");

  uint8_t buff[1024];

  unsigned long timeout = millis();

  while (https.connected() && (stream->available() > 0 || Update.hasError() == false)) {
    if (stream->available()) {
        int c = stream->readBytes(buff, sizeof(buff));
        if (c > 0) Update.write(buff, c);
        timeout = millis();
    }

    if (millis() - timeout > 30000) {  // 30 秒沒資料就中斷
        Serial.println("OTA timeout");
        break;
    }
    delay(1);
  }

  if (Update.end()) {
    if (Update.isFinished()) {
        Serial.println("OTA 成功，開始回報更新...");

        // 確保 reportUpdate 結束才重啟
        reportUpdate(version);  

        Serial.println("重啟中...");
        delay(500); 
        ESP.restart();

    } else {
        Serial.println("OTA 未完成");
    }
  } else {
    Update.printError(Serial);
  }
}
void reportUpdate(String version) {

  WiFiClientSecure client;
  client.setCACert(root_ca);
  client.setCertificate(device_cert);
  client.setPrivateKey(device_key);

  HTTPClient https;

  String url = "https://customer-agent.local:5000/report_update";

  if (!https.begin(client, url)) {
    Serial.println("report begin failed");
    return;
  }

  https.addHeader("Content-Type", "application/json");

  String payload = "{\"version\":\"" + version + "\"}";

  int httpCode = https.POST(payload);
  
  if (httpCode > 0 && httpCode == 200) {
      Serial.println("Update report success");
  } else {
      Serial.printf("Update report failed: %d\n", httpCode);
  }
  https.end();
}


bool registerDevice() {

  //每次 loop 都建立新的 client
  WiFiClientSecure tlsClient;
  
  tlsClient.setCACert(root_ca);
  tlsClient.setCertificate(device_cert);
  tlsClient.setPrivateKey(device_key);
  
  HTTPClient https;

  Serial.println("Connecting HTTPS (mTLS)..."); 

  if (!https.begin(tlsClient, "https://customer-agent.local:5000/register_device")) {
    Serial.println("HTTPS begin failed!");
    delay(3000);
    return false;
  }

  String mac = WiFi.macAddress();
  mac.toLowerCase();

  String payload = "{\"mac_address\":\"" + mac + "\"}";
  Serial.println("Request sent");
  Serial.print("MAC Address: ");
  Serial.println(mac);
  Serial.print("Payload: ");
  Serial.println(payload);

  https.addHeader("Content-Type", "application/json");

  int httpCode = https.POST(payload);

  if (httpCode > 0) {
    Serial.printf("HTTP Response code: %d\n", httpCode);

    int len = https.getSize();
    Serial.printf("Response length: %d\n", len);

    String response = https.getString();
    Serial.println("Server response:");
    Serial.println(response);

    https.end();

      if (httpCode == 200) {
        Serial.println("Register success");
        return true;
      } 
      else {
        Serial.println("Register failed (non-200), retrying...");
        return false;
      }

    } 
    else {
    Serial.printf("HTTPS POST failed: %s\n", https.errorToString(httpCode).c_str());
    https.end();
    return false;
    }

    delay(3000);
}

void setup() {
  
  Serial.begin(115200);
  
  /*
  // 開啟 TLS/SSL 詳細 log
  esp_log_level_set("mbedtls", ESP_LOG_VERBOSE);
  esp_log_level_set("ssl_client", ESP_LOG_VERBOSE); 
  esp_log_level_set("transport_base", ESP_LOG_VERBOSE); 
  esp_log_level_set("esp-tls", ESP_LOG_VERBOSE); 
  esp_log_level_set("*", ESP_LOG_VERBOSE);
  // 開始連線 WiFi 並等候成功
  */
  
  WiFiManager wm;

  wm.setConnectTimeout(20);

  // 如果沒有設定過 WiFi，ESP32 會建立 AP
  bool res = wm.autoConnect("ESP32-Setup");

  if(!res) {
    Serial.println("Open config portal");
    wm.startConfigPortal("ESP32-Setup");
  }
  
  Serial.println("ESP32 已連線");
  Serial.print("IP 地址：");
  Serial.println(WiFi.localIP());
  
  // NTP 時間同步
  configTime(8 * 3600, 0, "pool.ntp.org", "time.nist.gov");

  Serial.print("同步時間中");
  time_t now = time(nullptr);

  while (now < 8 * 3600 * 2) {  // 等到時間合理（避免1970）
    delay(500);
    Serial.print(".");
    now = time(nullptr);
  }

  Serial.println("\n時間同步完成");

  struct tm timeinfo;
  gmtime_r(&now, &timeinfo);
  Serial.printf("目前時間: %s\n", asctime(&timeinfo));

  // 啟動 mDNS

  if (!MDNS.begin("esp32client")) {
      Serial.println("mDNS 啟動失敗");
  } else {
      MDNS.addService("http", "tcp", 80);
      Serial.println("mDNS 已啟動");
  }  
  
  // 等一下讓 mDNS 註冊完成
  delay(2000);
 
  // server.on(path, method, handlerFunction, uploadFunction);
  // path const char* 要處理的 URL 路徑，例如 "/update"
  // method  HTTPMethod  HTTP 方法（如 HTTP_GET、HTTP_POST）
  // handlerFunction std::function<void()>（可用 lambda）處理「不含上傳檔案」的http請求（例如純 JSON、HTML 表單等）這裡用了[](){}表示不用(不可省略)
  // uploadFunction  THandlerFunction 專門處理檔案上傳事件（如 OTA 韌體）這裡傳了 handleFirmwareUpload
  
  server.on("/trigger_update", HTTP_POST, handleTriggerUpdate );
  server.begin();
  // 啟動 HTTP Server
  Serial.println("準備接收韌體更新...");

  pinMode(LED_BUILTIN, OUTPUT);
}

void loop() {
  // 持續處理用戶端的 HTTP 請求（如上傳韌體）
  digitalWrite(LED_BUILTIN, HIGH);  // 亮
  delay(1000);
  digitalWrite(LED_BUILTIN, LOW);   // 滅
  delay(1000);
  
  server.handleClient();
  delay(1);
  static bool registered = false;
  static unsigned long lastTry = 0;

  if (!registered && millis() - lastTry > 3000) {
    lastTry = millis();
    registered = registerDevice();
  }

   if (shouldUpdate) {
    shouldUpdate = false;

    Serial.println("開始執行 OTA...");
    performOTA(pendingVersion);
  }
}
