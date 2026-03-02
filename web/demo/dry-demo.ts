/**
 * Playwright script to record DRY analysis demo.
 *
 * Shows the Analyze DRY → Apply All workflow in SnippetManager.
 * Prerequisites: globalSetup seeds showcase agents and configures groq.
 *
 * Run with:
 *   # Terminal 1: Start server
 *   uv run voicetest demo --serve
 *
 *   # Terminal 2: Run recording (from web/ directory)
 *   mise exec -- bunx playwright test --project=dry
 *
 * Convert to GIF:
 *   ffmpeg -i dry-demo.webm -vf "fps=10,scale=1200:-1" dry-demo.gif
 */

import { test } from "@playwright/test";

test("record DRY analysis demo", async ({ page }) => {
  // Find the Meridian Insurance agent (created by globalSetup)
  const agents = await (await page.request.get("/api/agents")).json();
  const meridian = agents.find(
    (a: { name: string }) => a.name === "Meridian Insurance",
  );
  if (!meridian) throw new Error("Meridian Insurance agent not found — did globalSetup run?");

  // Navigate directly to the agent's config view
  await page.goto(`/#/agent/${meridian.id}/config`);
  await page.waitForSelector("section.general-prompt", { timeout: 10000 });
  await page.waitForTimeout(2000);

  // Scroll to the Snippets section
  const snippetsSection = page.locator("section.snippets-section");
  await snippetsSection.scrollIntoViewIfNeeded();
  await page.waitForTimeout(1000);

  // Click "Analyze DRY" button
  await page.click('button:has-text("Analyze DRY")');

  // Wait for DRY analysis results to render, then scroll to show them
  const dryResults = page.locator("div.dry-results");
  await dryResults.waitFor({ timeout: 30000 });
  await dryResults.scrollIntoViewIfNeeded();
  await page.waitForTimeout(3000);

  // Click "Apply All (N)" button
  await page.click('div.dry-header button:has-text("Apply All")');
  await page.waitForTimeout(1500);

  // Scroll down to show the newly applied snippets
  const snippetsList = page.locator("section.snippets-section .snippet-item, section.snippets-section table");
  if ((await snippetsList.count()) > 0) {
    await snippetsList.last().scrollIntoViewIfNeeded();
  } else {
    // Fallback: scroll the snippets section to the bottom
    await snippetsSection.evaluate((el) => el.scrollTop = el.scrollHeight);
  }
  await page.waitForTimeout(3000);
});
