import { defineConfig, devices } from '@playwright/test'

// Focused UI regressions, independent of the Python appliance fixture.
export default defineConfig({
  testDir: './e2e',
  testMatch: ['poster-loading.spec.js', 'mobile-layout.spec.js'],
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:8766', screenshot: 'only-on-failure' },
  projects: [
    { name: 'mobile-webkit', use: { ...devices['iPhone 13'] } },
    ...['en', 'de', 'fr'].map(language => ({ name: `mobile-webkit-${language}`, testMatch: 'mobile-layout.spec.js', metadata: { language }, use: { ...devices['iPhone 13'] } })),
    { name: 'small-mobile-webkit', testMatch: 'mobile-layout.spec.js', use: { ...devices['iPhone SE'] } },
    { name: 'desktop-webkit', use: { ...devices['Desktop Safari'] } },
  ],
  webServer: {
    command: 'npm run preview -- --host 127.0.0.1 --port 8766 --strictPort',
    url: 'http://127.0.0.1:8766',
    reuseExistingServer: false,
  },
})
