/**
 * Playwright global teardown: remove the temp database created by global-setup.
 */

import * as fs from "fs";
import * as os from "os";
import * as path from "path";

const DB_PATH_FILE = path.join(os.tmpdir(), "voicetest-e2e-db-path.txt");

export default function globalTeardown() {
  try {
    const tmpDir = fs.readFileSync(DB_PATH_FILE, "utf-8").trim();
    if (tmpDir && fs.existsSync(tmpDir)) {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
    fs.unlinkSync(DB_PATH_FILE);
  } catch {
    // Best-effort cleanup
  }
}
