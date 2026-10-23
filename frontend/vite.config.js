import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

const apiTarget = process.env.VITE_API_TARGET || 'http://127.0.0.1:8080'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/health': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
})
