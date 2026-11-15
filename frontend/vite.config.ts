import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// В разработке /api проксируется на бэкенд (uvicorn на 8790), в проде фронт раздаёт сам FastAPI.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:8790' } },
})
