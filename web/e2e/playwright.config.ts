import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: "**/*.e2e.ts",
  timeout: 15000,
  expect: {
    timeout: 5000,
  },
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: "http://localhost:8000",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "cd .. && uv run voicetest demo --serve",
    url: "http://localhost:8000",
    reuseExistingServer: !process.env.CI,
    timeout: 15000,
  },
});
