/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Base path matches the GitHub Pages project URL: https://<user>.github.io/deal-flow-mvp/
// Deep links work because routing uses the URL hash (HashRouter). Overridable
// via VITE_BASE_PATH so a build served from a domain root (e.g. the Render
// static site) can set it to '/' — see README's Render deployment section.
export default defineConfig({
  base: process.env.VITE_BASE_PATH || '/deal-flow-mvp/',
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
