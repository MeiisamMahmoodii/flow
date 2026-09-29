import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const backend = process.env.VNFLOW_BACKEND ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: backend, timeout: 0, proxyTimeout: 0 },
      '/files': backend,
      '/ws': { target: backend.replace('http', 'ws'), ws: true },
    },
  },
})
