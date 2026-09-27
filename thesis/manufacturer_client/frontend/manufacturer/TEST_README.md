# 前端測試框架

本文件說明 manufacturer 前端專案的測試架構與使用方式。測試目標為驗證韌體上傳與查詢相關的 React 元件行為，所有測試均不連接真實後端，API 呼叫全部以 mock 方式攔截。

## 快速開始

```bash
# 進入專案目錄
cd c:/Users/ailab/projects/Thesis/thesis/manufacturer_client/frontend/manufacturer

# 執行所有測試
npm test

# 執行所有測試一次（非監聽模式）
npx vitest run

# 執行單一測試檔案
npx vitest run src/components/FirmwareUpload.test.tsx

# 監聽模式（開發時使用）
npx vitest
```

## 測試結果

目前測試狀態：

- **4 個測試檔案** 全部通過
- **52 個測試案例** 全部通過

測試數量會隨著功能新增而增長，以上數字僅反映目前狀態。

## 測試文件清單

| 測試檔案 | 測試數量 | 測試對象 |
|---------|---------|---------|
| `src/App.test.tsx` | 17 | App 元件整體集成測試 |
| `src/components/FirmwareUpload.test.tsx` | 14 | 韌體上傳表單元件 |
| `src/components/UploadStatus.test.tsx` | 7 | 上傳狀態顯示元件 |
| `src/components/FirmwareHistory.test.tsx` | 14 | 韌體歷史記錄元件 |
| **總計** | **52** | **4 個測試檔案** |

## 測試涵蓋範圍

### App（17 個測試）

App 元件負責協調上傳表單、狀態顯示與歷史記錄三個子元件，並處理與後端 API 的完整互動流程。

**提交資格驗證**

- 版本號為空時，上傳按鈕應停用
- 未選擇檔案時，上傳按鈕應停用
- 同時提供版本號與檔案時，上傳按鈕應啟用

**表單欄位互動**

- 選擇檔案後正確顯示檔案名稱
- 版本號為空時顯示「No file selected」
- 輸入版本號後清除版本驗證錯誤
- 變更裝置類型後清除裝置類型驗證錯誤

**API 整合流程**

- 成功上傳：呼叫 `POST /internal/manufacturer/upload`，確認 HTTP method、FormData 欄位（version、device_type、firmware_file）均正確
- 成功上傳但回應無 `Message` 欄位時，使用預設成功訊息
- 成功上傳後觸發 `firmware-history-updated` 事件，通知歷史記錄元件刷新
- HTTP 400 錯誤時顯示「Upload failed: invalid request」
- HTTP 500 錯誤時顯示「Upload failed: manufacturer service error」
- HTTP 404 等非 400/500 錯誤時顯示通用錯誤訊息
- fetch 拒絕（網路錯誤）時顯示「Unable to connect to manufacturer service.」
- API 回應 JSON 解析失敗時不崩潰，仍顯示預設成功訊息
- 400 錯誤時不應觸發 `firmware-history-updated` 事件
- FormData 中不含有敏感金鑰（如 `firmware_key`）

### FirmwareUpload（14 個測試）

FirmwareUpload 元件負責渲染韌體上傳表單，包含版本輸入、裝置類型選擇與檔案選取。

- 版本輸入框正確顯示當前值
- 裝置類型選擇器包含 esp32 選項且預設值為 esp32
- 未選擇檔案時顯示「No file selected」
- 選擇檔案後顯示檔案名稱與大小
- 版本輸入變更時呼叫 `onVersionChange` callback
- 裝置類型變更時呼叫 `onDeviceTypeChange` callback
- 檔案選取變更時呼叫 `onFileChange` callback
- 點擊上傳按鈕時呼叫 `onUpload` callback
- `isSubmitDisabled=true` 時上傳按鈕停用
- `isSubmitDisabled=false` 時上傳按鈕啟用
- 存在版本驗證錯誤時顯示錯誤訊息
- 存在裝置類型驗證錯誤時顯示錯誤訊息
- 存在檔案驗證錯誤時顯示錯誤訊息
- 驗證錯誤時各輸入欄位具有 `aria-invalid="true"` 屬性

### UploadStatus（7 個測試）

UploadStatus 元件負責顯示上傳進度與結果，支援四種狀態與 IOTA Explorer 物件連結。

- 正確顯示狀態徽標文字與狀態訊息
- Ready 狀態應用 `.status-badge.ready` class
- Uploading 狀態應用 `.status-badge.uploading` class
- Success 狀態應用 `.status-badge.success` class
- Error 狀態應用 `.status-badge.error` class
- 提供有效 `objectId` 時顯示 IOTA Explorer 外部連結（正確 href、target="_blank"、rel="noopener noreferrer"）
- `objectId` 為 undefined 或空字串時不渲染連結元素

### FirmwareHistory（14 個測試）

FirmwareHistory 元件負責從後端取得並顯示韌體上傳歷史記錄，支援分頁與即時刷新。

**資料載入與顯示**

- 初始載入期間顯示「Loading firmware history...」
- 成功取得歷史記錄後正確渲染版本號、裝置大小（bytes 格式）與上傳狀態
- NTP 時間戳記（如 3820540800）正確轉換為 Asia/Taipei 時區顯示（2021-01-25 13:20:00）
- 後端回應失敗（HTTP 非 200）時顯示「Unable to load firmware history.」

**分頁功能**

- 成功載入後顯示分頁資訊（如「Page 1 / 1」）
- 存在 Object ID 時顯示 IOTA Explorer 連結
- Object ID 為空時顯示「-」
- 初始載入時 fetch 攜帶正確的分頁參數（`page=1`）
- 多頁時 Next 按鈕啟用
- 第一頁時 Previous 按鈕停用
- 最後一頁時 Next 按鈕停用
- 點擊 Next 後跳轉至下一頁並重新 fetch 正確頁碼
- 點擊 Previous 後返回上一頁並重新 fetch 正確頁碼

**事件整合**

- 收到 `firmware-history-updated` 自訂事件後重新取得歷史記錄

## 技術棧

| 套件 | 版本 |
|-----|------|
| Vitest | 5.0.1 |
| jsdom | 29.1.1 |
| @testing-library/react | 16.3.3 |
| @testing-library/jest-dom | 7.0.1 |
| @testing-library/user-event | 14.6.7 |
| React | 19.2.8 |

## 測試設定

### vitest.config.ts

```typescript
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    globals: true,
    testEnvironmentOptions: {
      html: '<html><body><div id="root"></div></body></html>',
    },
  },
})
```

設定說明：

- **environment: jsdom** — 模擬瀏覽器環境，使 React 元件得以正確渲染
- **setupFiles** — 執行 `src/test-setup.ts`，確保每項測試完成後清理 DOM
- **globals: true** — 無需匯入 `describe`、`it`、`expect` 即可直接使用
- **testEnvironmentOptions** — 提供基礎 HTML 骨架，`#root` 為 React 掛載點

### src/test-setup.ts

```typescript
import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => {
  cleanup()
})
```

設定說明：

- `@testing-library/jest-dom/vitest` — 匯入擴充斷言（如 `toBeInTheDocument`、`toBeDisabled`）
- `afterEach(cleanup)` — 每次測試結束後移除 DOM 樹，防止測試間互相干擾

## 測試策略與最佳實踐

- **Mock API 呼叫**：使用 `vi.fn()` 與 `vi.mock()` 攔截 `fetch`，避免依賴真實後端
- **DOM 清理**：透過 `afterEach(cleanup)` 確保每個測試擁有乾淨的 DOM 環境
- **非同步驗證**：使用 `waitFor` 等待非同步 UI 更新（如 API 回應後的狀態變更）
- **使用者操作模擬**：優先使用 `userEvent`（如 `userEvent.upload`、`userEvent.click`）模擬真實使用者互動，而非直接觸發 DOM 事件
- **語意化 Selector**：優先使用 `getByRole`、`getByLabelText` 等語意化選取器；在必要時才使用 `getByTestId`；避免過度依賴 CSS class、tag 名稱或元件內部實作細節
- **行為優先**：測試元件的使用者可觀察行為與 UI 輸出結果，而不是元件內部的實作細節
- **邊界條件**：針對 API 失敗（400、500、404、網路錯誤、JSON 解析失敗）分別編寫測試，確保錯誤處理路徑覆蓋完整

## 注意事項

- 測試不連接真實後端服務，所有 API 請求均透過 mock 攔截
- 不執行真實網路請求，測試結果不受後端服務狀態影響
- 測試主要驗證 React 元件的 UI 行為、使用者互動與事件處理
- 若需要額外測試元件，可參考現有測試檔案的編寫風格
