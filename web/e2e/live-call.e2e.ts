/**
 * E2E tests for live voice calls.
 *
 * Tests the call UI flow: starting a call, viewing transcript, ending a call.
 * Requires LiveKit server to be running.
 *
 * Run with:
 *   cd web && mise exec -- bunx playwright test live-call.e2e.ts --config=e2e/playwright.config.ts
 */

import { test, expect } from "@playwright/test";

// Check if LiveKit is available before running tests
async function isLiveKitAvailable(baseURL: string): Promise<boolean> {
  try {
    const response = await fetch(`${baseURL}/api/livekit/status`);
    if (!response.ok) return false;
    const data = await response.json();
    return data.available === true;
  } catch {
    return false;
  }
}

test.describe("Live Voice Calls", () => {
  test.setTimeout(60000); // Longer timeout for call operations

  test.beforeEach(async ({ page, baseURL }) => {
    // Skip all tests if LiveKit is not available
    const available = await isLiveKitAvailable(baseURL || "http://localhost:8000");
    test.skip(!available, "LiveKit server not available");

    // Grant microphone permissions to avoid permission prompts
    await page.context().grantPermissions(["microphone"]);
  });

  test("Talk button shows LiveKit status", async ({ page }) => {
    await page.goto("/");

    // Load demo agent if needed
    const agentList = page.locator(".agent-list");
    const hasAgents = await agentList.locator(".agent-item").count();

    if (hasAgents === 0) {
      // Load demo
      await page.click("button:has-text('Load Demo')");
      await expect(agentList).toContainText("Demo Healthcare Agent", { timeout: 10000 });
    }

    // Click on an agent
    await agentList.locator(".agent-item").first().click();

    // Look for the Talk button or CallView component
    // It should show "Talk to Agent" when LiveKit is available
    await expect(page.locator("button:has-text('Talk to Agent')")).toBeVisible({ timeout: 10000 });
  });

  test("starting a call shows call panel", async ({ page }) => {
    await page.goto("/");

    // Load demo agent
    const agentList = page.locator(".agent-list");
    const hasAgents = await agentList.locator(".agent-item").count();

    if (hasAgents === 0) {
      await page.click("button:has-text('Load Demo')");
      await expect(agentList).toContainText("Demo Healthcare Agent", { timeout: 10000 });
    }

    // Select an agent
    await agentList.locator(".agent-item").first().click();

    // Wait for Talk button to be ready
    const talkButton = page.locator("button:has-text('Talk to Agent')");
    await expect(talkButton).toBeVisible({ timeout: 10000 });
    await expect(talkButton).toBeEnabled();

    // Start the call
    await talkButton.click();

    // Should show connecting state
    await expect(page.locator("text=Connecting")).toBeVisible({ timeout: 5000 });

    // Should show call panel with "Live Call" indicator
    await expect(page.locator(".call-panel")).toBeVisible({ timeout: 15000 });
    await expect(page.locator("text=Live Call")).toBeVisible();

    // Should show call controls (Mute and End buttons)
    await expect(page.locator("button:has-text('Mute')")).toBeVisible();
    await expect(page.locator("button:has-text('End')")).toBeVisible();
  });

  test("ending a call closes the call panel", async ({ page }) => {
    await page.goto("/");

    // Load demo agent
    const agentList = page.locator(".agent-list");
    const hasAgents = await agentList.locator(".agent-item").count();

    if (hasAgents === 0) {
      await page.click("button:has-text('Load Demo')");
      await expect(agentList).toContainText("Demo Healthcare Agent", { timeout: 10000 });
    }

    await agentList.locator(".agent-item").first().click();

    // Start call
    const talkButton = page.locator("button:has-text('Talk to Agent')");
    await expect(talkButton).toBeVisible({ timeout: 10000 });
    await talkButton.click();

    // Wait for call panel
    await expect(page.locator(".call-panel")).toBeVisible({ timeout: 15000 });

    // End the call
    await page.locator("button:has-text('End')").click();

    // Call panel should disappear
    await expect(page.locator(".call-panel")).not.toBeVisible({ timeout: 5000 });

    // Talk button should be visible again
    await expect(page.locator("button:has-text('Talk to Agent')")).toBeVisible();
  });

  test("mute button toggles mute state", async ({ page }) => {
    await page.goto("/");

    // Load demo agent
    const agentList = page.locator(".agent-list");
    const hasAgents = await agentList.locator(".agent-item").count();

    if (hasAgents === 0) {
      await page.click("button:has-text('Load Demo')");
      await expect(agentList).toContainText("Demo Healthcare Agent", { timeout: 10000 });
    }

    await agentList.locator(".agent-item").first().click();

    // Start call
    await page.locator("button:has-text('Talk to Agent')").click();
    await expect(page.locator(".call-panel")).toBeVisible({ timeout: 15000 });

    // Initially should show "Mute"
    const muteButton = page.locator(".call-controls button").first();
    await expect(muteButton).toHaveText("Mute");

    // Click to mute
    await muteButton.click();
    await expect(muteButton).toHaveText("Unmute");

    // Click to unmute
    await muteButton.click();
    await expect(muteButton).toHaveText("Mute");

    // Cleanup
    await page.locator("button:has-text('End')").click();
  });

  test("transcript updates appear in call panel", async ({ page }) => {
    // This test verifies WebSocket connectivity and transcript display
    // It won't have actual speech but should show the empty state

    await page.goto("/");

    // Load demo agent
    const agentList = page.locator(".agent-list");
    const hasAgents = await agentList.locator(".agent-item").count();

    if (hasAgents === 0) {
      await page.click("button:has-text('Load Demo')");
      await expect(agentList).toContainText("Demo Healthcare Agent", { timeout: 10000 });
    }

    await agentList.locator(".agent-item").first().click();

    // Start call
    await page.locator("button:has-text('Talk to Agent')").click();
    await expect(page.locator(".call-panel")).toBeVisible({ timeout: 15000 });

    // Should show "Start speaking..." when no transcript yet
    await expect(page.locator(".transcript")).toBeVisible();
    await expect(page.locator("text=Start speaking")).toBeVisible();

    // Cleanup
    await page.locator("button:has-text('End')").click();
  });
});
