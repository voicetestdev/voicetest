/**
 * Playwright global setup.
 *
 * DB isolation is handled in playwright.config.ts (which creates the
 * temp DB path and passes it via webServer.env) so the setup here is
 * intentionally empty.
 */

export default function globalSetup() {
  // no-op — DB path created in playwright.config.ts
}
