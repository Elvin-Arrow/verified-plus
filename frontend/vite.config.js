import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// FE-01: app scaffolding. https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
  },
})
