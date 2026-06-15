import react from '@vitejs/plugin-react'
import regen from 'regen-ui/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  base: './',
  plugins: [regen(), react()],
  build: {
    outDir: 'dist/client',
    emptyOutDir: true
  },
  optimizeDeps: {
    include: ['eventemitter3', 'use-sync-external-store/shim', 'use-sync-external-store/shim/with-selector']
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:3003'
    }
  }
})
