/**
 * Playwright script to record web UI demo.
 *
 * Run with:
 *   # Terminal 1: Start server
 *   uv run voicetest demo --serve
 *
 *   # Terminal 2: Run recording (from web/ directory)
 *   mise exec -- bunx playwright test
 *
 * Convert to GIF:
 *   ffmpeg -i web-demo.webm -vf "fps=10,scale=1200:-1" web-demo.gif
 */

import { test } from "@playwright/test";

test("record web UI demo", async ({ page }) => {
  // Navigate to the app (starts on import view when no agents exist)
  await page.goto("/");
  await page.waitForTimeout(1000);

  // Click Load Demo button
  await page.click("button.demo-button");
  await page.waitForTimeout(2000);

  // Should now be on the agent config view
  // Navigate to Tests tab
  await page.click("text=Tests");
  await page.waitForTimeout(1000);

  // Select first 3 tests by clicking checkboxes
  const checkboxes = page.locator('input[type="checkbox"]');
  const count = await checkboxes.count();
  for (let i = 0; i < Math.min(3, count); i++) {
    await checkboxes.nth(i).click();
    await page.waitForTimeout(300);
  }

  await page.waitForTimeout(500);

  // Click Run Selected button
  await page.click("text=Run Selected");
  await page.waitForTimeout(1000);

  // Wait for tests to complete (watch for status changes)
  await page.waitForTimeout(15000);

  // Click on a result to see details
  const results = page.locator('[class*="result"]');
  if ((await results.count()) > 0) {
    await results.first().click();
    await page.waitForTimeout(2000);
  }
});
