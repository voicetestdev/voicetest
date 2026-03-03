/**
 * Playwright global setup: create an isolated temp database for e2e tests.
 *
 * Sets VOICETEST_DB_PATH to a temp file so tests run against a clean DB
 * that doesn't interfere with development data.
 */

import * as fs from "fs";
import * as os from "os";
import * as path from "path";

const DB_PATH_FILE = path.join(os.tmpdir(), "voicetest-e2e-db-path.txt");

export default function globalSetup() {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "voicetest-e2e-"));
  const dbPath = path.join(tmpDir, "e2e-test.duckdb");

  // Set env var for the server process Playwright will spawn
  process.env.VOICETEST_DB_PATH = dbPath;

  // Persist the path so global-teardown can clean it up
  fs.writeFileSync(DB_PATH_FILE, tmpDir);
}
