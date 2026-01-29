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

  // Select first 3 tests by clicking row checkboxes (skip header checkbox)
  const rowCheckboxes = page.locator('tbody input[type="checkbox"]');
  const checkboxCount = await rowCheckboxes.count();
  for (let i = 0; i < Math.min(3, checkboxCount); i++) {
    await rowCheckboxes.nth(i).click();
    await page.waitForTimeout(300);
  }
  await page.waitForTimeout(500);

  // Click Run Selected button
  await page.click("button:has-text('Run Selected')");
  await page.waitForTimeout(500);

  // Click Runs tab to ensure navigation (workaround for auto-switch issue)
  await page.click('button.tab-item:has-text("Runs")');
  await page.waitForTimeout(1000);

  // Poll for the results list to appear
  for (let i = 0; i < 20; i++) {
    const resultsList = await page.locator(".result-select-btn").count();
    if (resultsList > 0) break;
    await page.waitForTimeout(500);
  }

  // Wait a moment then click the first test result to show conversation
  await page.waitForTimeout(500);
  const resultBtn = page.locator(".result-select-btn").first();
  if ((await resultBtn.count()) > 0) {
    await resultBtn.click();
  }

  // Watch the conversation flow
  await page.waitForTimeout(8000);
});
