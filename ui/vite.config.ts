import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/health': 'http://localhost:8000',
      '/pipeline': 'http://localhost:8000',
      '/scenarios': 'http://localhost:8000',
      '/evaluation': 'http://localhost:8000',
    },
  },
})
