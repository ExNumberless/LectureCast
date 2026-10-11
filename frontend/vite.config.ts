/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Same-origin /api like CloudFront in AWS, so no CORS. API_PROXY_TARGET is set by docker-compose.
    proxy: {
      '/api': process.env.API_PROXY_TARGET ?? 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
  },
})
