import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // FastAPI dev server (`uvicorn web.api.app:app`). Relative fetches
      // from the browser avoid CORS entirely -- see web/api/auth.py's
      // Origin check on the mutation routes. `changeOrigin` only rewrites
      // the outgoing `Host` header, not `Origin` -- the browser's real
      // `Origin` (e.g. `http://localhost:5173`) still reaches FastAPI
      // unchanged and never matches `request.url.netloc` (which follows
      // the rewritten `Host`), so every mutation 403s in dev without the
      // rewrite below.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq) => {
            proxyReq.setHeader('origin', 'http://127.0.0.1:8000')
          })
        },
      },
    },
  },
})
