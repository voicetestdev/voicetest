/**
 * E2E tests for mermaid graph rendering on the agent config page.
 *
 * Regression test: agents with {{template_variables}} in prompts should
 * render the mermaid graph without errors when imported as a linked file.
 *
 * Run with:
 *   cd web && mise exec -- bunx playwright test --config=e2e/playwright.config.ts
 */

import { test, expect } from "@playwright/test";
import { dirname, resolve } from "path";
import { fileURLToPath } from "url";
import { deleteAgentsByPrefix } from "./helpers";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const TEST_PREFIX = "e2e_graph_linked_";

test.describe("Graph Rendering", () => {
  test.setTimeout(30000);

  test.afterEach(async ({ baseURL }) => {
    await deleteAgentsByPrefix(baseURL!, TEST_PREFIX);
  });

  test("graph renders for linked file agent with template variables", async ({
    page,
  }) => {
    const agentName = `${TEST_PREFIX}${Date.now()}`;

    // Resolve the fixture path relative to the project root
    const fixturePath = resolve(
      __dirname,
      "../../tests/fixtures/retell/sample_llm_with_variables.json",
    );

    await page.goto("/");
    await expect(page.locator("body")).toBeVisible();

    // Navigate to import
    await page.click("button:has-text('Import Agent')");
    await expect(page.locator("h2:has-text('Import')")).toBeVisible();

    // Expand "Link to server file"
    await page.click("button:has-text('Link to server file')");

    // Fill in the server path
    const pathInput = page.locator("input[placeholder='/path/to/agent.json']");
    await expect(pathInput).toBeVisible();
    await pathInput.fill(fixturePath);
    // Trigger blur so name auto-fills
    await pathInput.blur();

    // Override the auto-filled name
    await page.locator("input[placeholder='Agent name']").fill(agentName);

    // Import
    await page.locator("main button:has-text('Import Agent')").click();

    // Wait for agent to appear in sidebar
    await expect(page.locator(".agent-list")).toContainText(agentName, {
      timeout: 10000,
    });

    // Should be on config view — wait for the graph SVG to render
    const mermaidContainer = page.locator(".mermaid-container");
    await expect(mermaidContainer).toBeVisible({ timeout: 10000 });

    const svg = mermaidContainer.locator("svg");
    await expect(svg).toBeVisible({ timeout: 10000 });

    // Verify the graph contains the node labels
    const svgContent = await svg.innerHTML();
    expect(svgContent).toContain("intro");
    expect(svgContent).toContain("identity_check");
    expect(svgContent).toContain("verify");
  });
});
