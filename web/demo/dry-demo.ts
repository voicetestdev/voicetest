/**
 * Playwright script to record DRY analysis demo.
 *
 * Shows the Analyze DRY → Apply All workflow in SnippetManager.
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
import dryAgent from "./dry-agent.json" with { type: "json" };

test("record DRY analysis demo", async ({ page }) => {
  // Create the demo agent via API
  const response = await page.request.post("/api/agents", {
    data: {
      name: "Meridian Claims Assistant",
      config: dryAgent,
      source: "retell-llm",
    },
  });

  if (!response.ok()) {
    throw new Error(`Failed to create agent: ${response.status()}`);
  }

  const agent = await response.json();

  // Navigate directly to the created agent's config view
  await page.goto(`/#/agent/${agent.id}/config`);
  await page.waitForSelector("section.general-prompt", { timeout: 10000 });
  await page.waitForTimeout(2000);

  // Scroll to the Snippets section
  const snippetsSection = page.locator("section.snippets-section");
  await snippetsSection.scrollIntoViewIfNeeded();
  await page.waitForTimeout(1000);

  // Click "Analyze DRY" button
  await page.click('button:has-text("Analyze DRY")');

  // Wait for DRY analysis results to render
  await page.waitForSelector("div.dry-results", { timeout: 30000 });
  await page.waitForTimeout(3000);

  // Click "Apply All (N)" button
  await page.click('div.dry-header button:has-text("Apply All")');
  await page.waitForTimeout(3000);
});
