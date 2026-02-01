/**
 * E2E tests for settings reactivity.
 *
 * These tests verify that settings changes properly reflect in the UI,
 * preventing regressions in Svelte 5 store reactivity.
 *
 * Run with:
 *   cd web && bunx playwright test --config=e2e/playwright.config.ts
 */

import { test, expect } from "@playwright/test";

test.describe("Settings Reactivity", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");

    // If no agents, load demo
    const demoButton = page.locator("button.demo-button");
    if (await demoButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      await demoButton.click();
      await expect(page.locator(".agent-list")).toBeVisible();
    }
  });

  test("settings toggle reflects changes immediately", async ({ page }) => {
    // Navigate to settings
    await page.click("button:has-text('Settings')");
    await expect(page.locator("h2:has-text('Settings')")).toBeVisible();

    // Find the test_model_precedence toggle
    const toggle = page.locator("#test-model-precedence");
    await expect(toggle).toBeVisible();

    // Get initial state
    const initialChecked = await toggle.isChecked();

    // Toggle the checkbox
    await toggle.click();

    // Verify the toggle state changed
    await expect(toggle).toBeChecked({ checked: !initialChecked });

    // Toggle back to original state for test cleanup
    await toggle.click();
    await expect(toggle).toBeChecked({ checked: initialChecked });
  });

  test("model settings handle null values correctly", async ({ page }) => {
    // Navigate to settings
    await page.click("button:has-text('Settings')");
    await expect(page.locator("h2:has-text('Settings')")).toBeVisible();

    // Find agent model input
    const agentModelInput = page.locator("#agent-model");
    await expect(agentModelInput).toBeVisible();

    // Store original value
    const originalValue = await agentModelInput.inputValue();

    // Clear the input (set to null)
    await agentModelInput.fill("");
    await expect(agentModelInput).toHaveValue("");

    // Set a value
    await agentModelInput.fill("test/model");
    await expect(agentModelInput).toHaveValue("test/model");

    // Restore original value for cleanup
    await agentModelInput.fill(originalValue);
  });

  test("settings store updates propagate after navigation", async ({ page }) => {
    // Navigate to settings
    await page.click("button:has-text('Settings')");
    await expect(page.locator("h2:has-text('Settings')")).toBeVisible();

    const maxTurnsInput = page.locator("#max-turns");
    const originalValue = await maxTurnsInput.inputValue();

    // Set a specific value
    await maxTurnsInput.fill("15");
    await expect(maxTurnsInput).toHaveValue("15");

    // Navigate to import view (always available in nav)
    await page.click("button:has-text('Import Agent')");
    await expect(page.locator("h2:has-text('Import')")).toBeVisible();

    // Navigate back to settings
    await page.click("button:has-text('Settings')");
    await expect(page.locator("h2:has-text('Settings')")).toBeVisible();

    // Verify the value persisted (store reactivity working)
    await expect(page.locator("#max-turns")).toHaveValue("15");

    // Reset for cleanup
    await page.locator("#max-turns").fill(originalValue);
  });
});

test.describe("Agent Config Reactivity", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");

    const demoButton = page.locator("button.demo-button");
    if (await demoButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      await demoButton.click();
      await expect(page.locator(".agent-list")).toBeVisible();
    }
  });

  test("agent name edit reflects changes immediately", async ({ page }) => {
    // Should be on agent config view after demo load
    const nameElement = page.locator(".editable-name");
    await expect(nameElement).toBeVisible();

    // Get original name
    const originalName = await nameElement.textContent();

    // Click to edit
    await nameElement.click();

    // Wait for input to appear
    const nameInput = page.locator(".name-input");
    await expect(nameInput).toBeVisible();

    // Change the name
    await nameInput.fill(`${originalName} (edited)`);
    await nameInput.blur();

    // Verify the name changed in the header
    await expect(page.locator(".editable-name")).toContainText("(edited)");

    // Verify it shows in the sidebar too (store reactivity)
    await expect(page.locator(".agent-list")).toContainText("(edited)");

    // Restore original name
    await page.locator(".editable-name").click();
    await page.locator(".name-input").fill(originalName!.trim());
    await page.locator(".name-input").blur();
  });

  test("agent LLM edit updates correctly", async ({ page }) => {
    // Select the Demo Healthcare Agent explicitly to ensure consistency
    await page.locator(".agent-list button", { hasText: "Demo Healthcare Agent" }).click();

    // Wait for the agent to load
    await expect(page.locator("h2")).toContainText("Demo Healthcare Agent");
    await expect(page.locator(".agent-info")).toBeVisible();

    // Find and click the LLM field to edit
    const llmField = page.locator(".editable-model");
    await expect(llmField).toBeVisible();

    // Get original value
    const originalValue = await llmField.textContent();

    // Click to edit
    await llmField.click();

    // Wait for input
    const modelInput = page.locator(".model-input");
    await expect(modelInput).toBeVisible();

    // Set a new value
    await modelInput.fill("openai/gpt-4o");
    await modelInput.blur();

    // Verify the change (wait for span to appear with new value)
    await expect(page.locator(".editable-model")).toContainText("openai/gpt-4o");

    // Wait a bit for the save to complete on the backend
    await page.waitForTimeout(500);

    // Navigate to tests and back to verify persistence
    await page.locator(".view-tabs button:has-text('Tests')").click();
    await expect(page.locator("h2:has-text('Tests')")).toBeVisible();

    await page.locator(".view-tabs button:has-text('Config')").click();
    await expect(page.locator(".agent-info")).toBeVisible();

    // Verify still shows the value (store reactivity)
    await expect(page.locator(".editable-model")).toContainText("openai/gpt-4o");

    // Restore original
    await page.locator(".editable-model").click();
    if (originalValue?.includes("Not set")) {
      await page.locator(".model-input").fill("");
    } else {
      await page.locator(".model-input").fill(originalValue!.trim());
    }
    await page.locator(".model-input").blur();
  });
});
