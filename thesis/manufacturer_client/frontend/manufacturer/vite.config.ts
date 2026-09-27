import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // History API -> Manufacturer Agent
      '/internal/agent': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) =>
          path.replace(/^\/internal\/agent/, ''),
      },

      // Upload API -> Manufacturer Client Service
      '/internal': {
        target: 'http://127.0.0.1:5002',
        changeOrigin: true,
      },
    },
  },
})