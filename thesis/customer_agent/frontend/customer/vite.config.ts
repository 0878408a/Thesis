import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // 把 /api 前綴轉發到 Customer Agent public server。
      // port 5000 是 mTLS（run_device_server）、port 5001 是 public（run_public_server）。
      // 5001 為 HTTPS（server-only TLS，使用本地自簽憑證 ecdsa_ca.pem，不需 client 憑證），
      // 因此 target 走 https://，並用 secure: false 跳過 Node 端自簽憑證驗證。
      '/api': {
        target: 'https://localhost:5001',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
