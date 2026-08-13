/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Base path matches the GitHub Pages project URL: https://<user>.github.io/deal-flow-mvp/
// Deep links work because routing uses the URL hash (HashRouter).
export default defineConfig({
  base: '/deal-flow-mvp/',
  plugins: [react()],
  test: {
    environment: 'jsdom',
    // Playwright owns everything under e2e/; vitest must not try to run a
    // browser spec in jsdom.
    exclude: ['node_modules/**', 'dist/**', 'e2e/**'],
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
    css: false,
  },
})
