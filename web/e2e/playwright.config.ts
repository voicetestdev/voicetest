import { defineConfig } from "@playwright/test";

// E2E tests run their own server on a dedicated port so they never
// conflict with a dev server and always start with a clean database
// (VOICETEST_DB_PATH is set by global-setup.ts).
const E2E_PORT = 8099;

export default defineConfig({
  testDir: ".",
  testMatch: "**/*.e2e.ts",
  globalSetup: "./global-setup.ts",
  globalTeardown: "./global-teardown.ts",
  timeout: 15000,
  expect: {
    timeout: 5000,
  },
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: `http://localhost:${E2E_PORT}`,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: `cd .. && uv run voicetest serve --port ${E2E_PORT}`,
    url: `http://localhost:${E2E_PORT}`,
    reuseExistingServer: false,
    timeout: 15000,
  },
});
