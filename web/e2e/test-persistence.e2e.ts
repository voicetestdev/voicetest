/**
 * E2E tests for test case persistence across agent switches.
 *
 * Regression test: imported tests should persist when switching between agents.
 *
 * Run with:
 *   cd web && mise exec -- bunx playwright test --config=e2e/playwright.config.ts
 */

import { test, expect } from "@playwright/test";

test.describe("Test Case Persistence", () => {
  // Use longer timeout for this test since it involves multiple imports
  test.setTimeout(30000);

  test("imported tests persist when switching between agents", async ({
    page,
  }) => {
    // Generate unique names to avoid conflicts with existing agents
    const timestamp = Date.now();
    const agent1Name = `e2e_billing_${timestamp}`;
    const agent2Name = `e2e_support_${timestamp}`;

    await page.goto("/");

    // Wait for page to load
    await expect(page.locator("body")).toBeVisible();

    // Import first agent
    await page.click("button:has-text('Import Agent')");
    await expect(page.locator("h2:has-text('Import')")).toBeVisible();

    // Use retell-llm format which is auto-detectable
    const agent1Config = JSON.stringify({
      general_prompt: "You are a billing support agent.",
      states: [
        {
          name: "greeting",
          state_prompt: "Greet the customer and ask how you can help with billing.",
          edges: [],
          tools: [],
        },
      ],
    });

    // Fill in agent name and config
    await page.locator("input[placeholder='Agent name']").fill(agent1Name);
    await page.locator("textarea").fill(agent1Config);

    // Click the submit button (not the nav button)
    await page.locator("main button:has-text('Import Agent')").click();

    // Wait for agent to be imported and selected (longer timeout for import)
    await expect(page.locator(".agent-list")).toContainText(agent1Name, {
      timeout: 10000,
    });

    // Navigate to tests view for agent 1
    await page.click("button:has-text('Tests')");
    await expect(page.locator("h2:has-text('Tests')")).toBeVisible();

    // Import test cases for agent 1
    await page.click("main button:has-text('Import')");
    await expect(page.locator(".modal")).toBeVisible();

    const testCases = JSON.stringify([
      {
        name: "Billing inquiry test",
        user_prompt: "Ask about a charge on your bill",
        metrics: ["Agent was helpful"],
        type: "llm",
      },
      {
        name: "Payment test",
        user_prompt: "Ask about making a payment",
        metrics: ["Agent provided payment info"],
        type: "llm",
      },
    ]);

    await page.locator(".modal textarea").fill(testCases);
    await page.click(".modal-footer button:has-text('Import')");

    // Wait for tests to appear (async import needs API roundtrips)
    await expect(page.locator("table")).toBeVisible({ timeout: 10000 });
    await expect(page.locator("table")).toContainText("Billing inquiry test");
    await expect(page.locator("table")).toContainText("Payment test");

    // Count the tests (should be 2)
    const testRowsAgent1 = page.locator("table tbody tr");
    await expect(testRowsAgent1).toHaveCount(2);

    // Import second agent
    await page.click("button:has-text('Import Agent')");
    await expect(page.locator("h2:has-text('Import')")).toBeVisible();

    // Use retell-llm format which is auto-detectable
    const agent2Config = JSON.stringify({
      general_prompt: "You are a technical support agent.",
      states: [
        {
          name: "support",
          state_prompt: "Help the customer with technical issues.",
          edges: [],
          tools: [],
        },
      ],
    });

    // Fill in agent name and config
    await page.locator("input[placeholder='Agent name']").fill(agent2Name);
    await page.locator("textarea").fill(agent2Config);

    // Click the submit button (not the nav button)
    await page.locator("main button:has-text('Import Agent')").click();

    // Wait for agent 2 to be selected (longer timeout for import)
    await expect(page.locator(".agent-list")).toContainText(agent2Name, {
      timeout: 10000,
    });

    // Navigate to tests view for agent 2 (should have no tests)
    await page.click("button:has-text('Tests')");
    await expect(page.locator("h2:has-text('Tests')")).toBeVisible();

    // Agent 2 should have no tests
    await expect(page.locator("text=No test cases")).toBeVisible();

    // Now switch back to agent 1 by clicking it in the sidebar
    await page.locator(".agent-list").getByText(agent1Name).click();

    // Navigate to tests view
    await page.click("button:has-text('Tests')");
    await expect(page.locator("h2:has-text('Tests')")).toBeVisible();

    // Tests should still be there
    await expect(page.locator("table")).toBeVisible();
    await expect(page.locator("table")).toContainText("Billing inquiry test");
    await expect(page.locator("table")).toContainText("Payment test");

    // Count should still be 2
    const testRowsAfterSwitch = page.locator("table tbody tr");
    await expect(testRowsAfterSwitch).toHaveCount(2);
  });
});
