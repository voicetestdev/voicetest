import * as fs from "fs";
import * as os from "os";
import * as path from "path";

import { defineConfig } from "@playwright/test";

// Create the temp DB path at config-evaluation time so it is guaranteed
// to be available when Playwright spawns the webServer process (the
// webServer may start before globalSetup runs).
const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "voicetest-e2e-"));
const dbPath = path.join(tmpDir, "e2e-test.duckdb");

// Persist the tmpDir path so global-teardown can clean it up
const DB_PATH_FILE = path.join(os.tmpdir(), "voicetest-e2e-db-path.txt");
fs.writeFileSync(DB_PATH_FILE, tmpDir);

const E2E_PORT = 8099;

export default defineConfig({
  testDir: ".",
  testMatch: "**/*.e2e.ts",
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
    env: {
      VOICETEST_DB_PATH: dbPath,
    },
  },
});
