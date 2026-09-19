import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end configuration for the interview demo path.
 *
 * Deliberately no `webServer`: the API and the web build have to be running
 * already (`make demo` or `scripts/dev_restart.sh`). A test harness that
 * starts its own stack tests a stack nobody demos from.
 */
export default defineConfig({
  testDir: './e2e',
  // The curated path runs a zone simulation and two load flows. Generous, but
  // still an upper bound the demo must stay inside.
  timeout: 180_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:3000',
    viewport: { width: 1600, height: 900 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // The image ships Chromium at a fixed path and blocks downloads.
        launchOptions: process.env.PLAYWRIGHT_CHROMIUM_PATH
          ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH }
          : {},
      },
    },
  ],
});
