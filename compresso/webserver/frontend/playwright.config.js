import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [['dot'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: 'http://127.0.0.1:8910/compresso',
    trace: 'on-first-retry',
    video: 'retain-on-failure',
  },
  webServer: {
    command: 'node ./scripts/serve-e2e.mjs',
    url: 'http://127.0.0.1:8910/compresso/',
    reuseExistingServer: false,
    timeout: 120_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'mobile-chromium',
      grep: /@(mobile|accessibility)/,
      use: { ...devices['Pixel 7'] },
    },
    {
      name: 'firefox-smoke',
      grep: /@cross-browser/,
      use: {
        ...devices['Desktop Firefox'],
        launchOptions: { timeout: 30_000 },
      },
    },
    {
      name: 'webkit-smoke',
      grep: /@cross-browser/,
      use: { ...devices['Desktop Safari'] },
    },
  ],
})
