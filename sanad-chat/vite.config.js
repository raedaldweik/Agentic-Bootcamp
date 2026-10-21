import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Standalone Sanad chat. In dev, /api is proxied to the FastAPI backend
// (`uvicorn main:app --port 8000` in ../backend). When no backend answers,
// the app falls back to its built-in showcase mode (see src/lib/api.js).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
});
