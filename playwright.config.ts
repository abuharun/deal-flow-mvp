import { defineConfig, devices } from '@playwright/test'

/**
 * Browser E2E against the REAL local stack: Postgres, the FastAPI app, and
 * the Vite dev server. Nothing is mocked at the network layer — the only
 * substitution anywhere is the analysis worker's provider, which runs as the
 * offline `local-stub` (see backend/app/services/local_stub_provider.py) so
 * the run needs no OpenAI credentials and produces identical, self-disclosed
 * placeholder text every time.
 *
 * Both servers are started by Playwright and inherit the backend's own safe
 * defaults (ENV=development, the local Postgres DSN, http://localhost:5173 as
 * the single allowed origin) — see backend/app/config.py. No .env is written:
 * the repo deliberately asserts backend/.env stays absent.
 *
 * One worker, no retries: this spec walks a single startup through one
 * lifecycle in one database, so parallelism or a silent retry would only
 * hide a real ordering bug.
 */

export const APP_ORIGIN = 'http://localhost:5173'
export const APP_BASE_PATH = '/deal-flow-mvp/'
// Not the backend's default 8000: that port is often taken by an unrelated
// local service, and the E2E must not depend on winning a race for it. The
// frontend is told about it through VITE_API_BASE_URL, and the backend is
// told to accept this origin through FRONTEND_ORIGINS.
export const API_PORT = 8020
export const API_ORIGIN = `http://localhost:${API_PORT}`

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [['list']],
  use: {
    baseURL: `${APP_ORIGIN}${APP_BASE_PATH}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `.venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port ${API_PORT}`,
      cwd: 'backend',
      env: { FRONTEND_ORIGINS: APP_ORIGIN, API_PUBLIC_URL: API_ORIGIN, FRONTEND_PUBLIC_URL: APP_ORIGIN },
      url: `${API_ORIGIN}/healthz`,
      reuseExistingServer: !process.env.CI,
      stdout: 'pipe',
      stderr: 'pipe',
      timeout: 60_000,
    },
    {
      command: 'npm run dev -- --port 5173 --strictPort',
      env: { VITE_API_BASE_URL: API_ORIGIN },
      url: `${APP_ORIGIN}${APP_BASE_PATH}`,
      reuseExistingServer: !process.env.CI,
      stdout: 'pipe',
      stderr: 'pipe',
      timeout: 60_000,
    },
  ],
})
