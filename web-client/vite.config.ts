/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_BASE || 'http://127.0.0.1:8006'
  return {
    plugins: react(),
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      host: '127.0.0.1',
      port: 5173,
      proxy: {
        '/api': { target: apiTarget, changeOrigin: true },
        '/images': { target: apiTarget, changeOrigin: true },
      },
    },
    build: {
      target: 'es2022',
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes('node_modules/react-markdown') || id.includes('node_modules/remark-')) return 'markdown'
            if (id.includes('node_modules/@tanstack/react-query')) return 'query'
            if (id.includes('node_modules/react') || id.includes('node_modules/react-router')) return 'react'
            return undefined
          },
        },
      },
    },
    test: {
      environment: 'jsdom',
      include: ['src/**/*.test.{ts,tsx}'],
      setupFiles: './src/test/setup.ts',
      css: true,
      coverage: {
        provider: 'v8',
        reporter: ['text', 'html'],
        thresholds: { lines: 80, functions: 80, branches: 80, statements: 80 },
      },
    },
  }
})
