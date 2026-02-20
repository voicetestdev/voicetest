/**
 * E2E tests for text chat with agent.
 *
 * Tests the chat UI flow: starting a chat, sending messages, ending a chat.
 * No LiveKit or audio infrastructure required.
 *
 * Run with:
 *   cd web && mise exec -- bunx playwright test live-chat.e2e.ts --config=e2e/playwright.config.ts
 */

import { test, expect } from "@playwright/test";

// Check if a demo agent exists, create one if not
async function ensureDemoAgent(baseURL: string): Promise<string> {
  const response = await fetch(`${baseURL}/api/demo`, { method: "POST" });
  const data = await response.json();
  return data.agent_id;
}

test.describe("Text Chat", () => {
  test.beforeEach(async ({ page, baseURL }) => {
    const agentId = await ensureDemoAgent(baseURL!);
    await page.goto(`/#agent=${agentId}`);
    await page.waitForSelector("text=Chat with Agent", { timeout: 10000 });
  });

  test("shows Chat with Agent button", async ({ page }) => {
    const chatButton = page.getByRole("button", { name: "Chat with Agent" });
    await expect(chatButton).toBeVisible();
  });

  test("starts a chat session", async ({ page }) => {
    const chatButton = page.getByRole("button", { name: "Chat with Agent" });
    await chatButton.click();

    // Should show the chat panel
    await expect(page.locator(".chat-panel")).toBeVisible({ timeout: 10000 });
    await expect(page.locator(".chat-status")).toContainText("Live Chat");
  });

  test("shows input area when chat is active", async ({ page }) => {
    await page.getByRole("button", { name: "Chat with Agent" }).click();
    await expect(page.locator(".chat-panel")).toBeVisible({ timeout: 10000 });

    const input = page.locator(".chat-input");
    await expect(input).toBeVisible();
    await expect(input).toHaveAttribute("placeholder", "Type a message...");
  });

  test("can end a chat session", async ({ page }) => {
    await page.getByRole("button", { name: "Chat with Agent" }).click();
    await expect(page.locator(".chat-panel")).toBeVisible({ timeout: 10000 });

    // Click End button
    await page.getByRole("button", { name: "End" }).click();

    // Should return to idle state with the start button
    await expect(page.getByRole("button", { name: "Chat with Agent" })).toBeVisible({
      timeout: 10000,
    });
  });
});
