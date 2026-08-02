import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      // 开发时可选：将 /api 与 /images 代理到后端，规避跨域与混合内容问题。
      // 通过环境变量 VITE_API_BASE 指定后端；未设置时默认线上服务器。
      '/api': {
        target: process.env.VITE_API_BASE || 'http://8.137.187.54:8006',
        changeOrigin: true,
      },
      '/images': {
        target: process.env.VITE_API_BASE || 'http://8.137.187.54:8006',
        changeOrigin: true,
      },
    },
  },
})
