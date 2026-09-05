import { defineConfig, devices } from '@playwright/test'
import { tmpdir } from 'node:os'
import path from 'node:path'

const backendPort = process.env.BACKEND_PORT || '8920'
const frontendPort = process.env.LIVE_E2E_PORT || '8911'
const pythonBin = process.env.PYTHON_BIN || 'python3.13'
const homeDir = process.env.LIVE_E2E_HOME_DIR || path.join(tmpdir(), `compresso-live-e2e-${backendPort}`)
process.env.LIVE_E2E_HOME_DIR = homeDir

export default defineConfig({
  testDir: './tests/e2e-live',
  timeout: 45_000,
  expect: {
    timeout: 15_000,
  },
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['dot'], ['html', { open: 'never' }]] : 'list',
  globalTeardown: './tests/e2e-live/global-teardown.mjs',
  use: {
    baseURL: `http://127.0.0.1:${frontendPort}/compresso`,
    trace: 'on-first-retry',
    video: 'retain-on-failure',
  },
  webServer: [
    {
      command: 'node ./scripts/start-live-backend.mjs',
      url: `http://127.0.0.1:${backendPort}/compresso/api/v2/healthcheck/readiness`,
      env: {
        BACKEND_PORT: backendPort,
        LIVE_E2E_HOME_DIR: homeDir,
        PYTHON_BIN: pythonBin,
      },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: 'node ./scripts/serve-e2e.mjs',
      url: `http://127.0.0.1:${frontendPort}/compresso/`,
      env: {
        COMPRESSO_BACKEND_URL: `http://127.0.0.1:${backendPort}`,
        PORT: frontendPort,
      },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
  projects: [
    {
      name: 'chrome-live-backend',
      use: {
        ...devices['Desktop Chrome'],
        channel: 'chrome',
      },
    },
  ],
})
