import { resolve } from 'node:path'
import { defineConfig, devices } from '@playwright/test'

const port = process.env.AIO_E2E_PORT || '8765'
export default defineConfig({
  testDir: './e2e',
  testMatch: 'journeys.spec.js',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: 60000,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { actionTimeout: 10000, navigationTimeout: 15000, baseURL: `http://127.0.0.1:${port}`, locale: 'en-US', timezoneId: 'Europe/Amsterdam', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
  webServer: {
    command: `${process.env.E2E_PYTHON || resolve('../.venv/bin/python')} ../scripts/e2e_server.py`,
    url: `http://127.0.0.1:${port}/health`,
    reuseExistingServer: false,
    timeout: 30000,
  },
})
