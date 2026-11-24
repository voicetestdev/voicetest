import { test, expect } from "@playwright/test";
import { deleteAgentsByPrefix } from "./helpers";

const TEST_PREFIX = "e2e_variable_picker_";

const extractOnlyVariableAgent = {
  source_type: "custom",
  entry_node_id: "extract",
  nodes: {
    extract: {
      id: "extract",
      state_prompt: "Collect the caller's color choice.",
      node_type: "extract",
      variables_to_extract: [
        {
          name: "selected_color",
          description:
            "If the caller accepts the suggested color, return the value from {{available_color}}.",
        },
      ],
      transitions: [],
    },
  },
};

test.describe("Variable Picker", () => {
  test.setTimeout(30000);

  test.afterEach(async ({ baseURL }) => {
    await deleteAgentsByPrefix(baseURL!, TEST_PREFIX);
  });

  test("lists variables used only in extraction descriptions", async ({
    page,
    baseURL,
  }) => {
    const agentName = `${TEST_PREFIX}${Date.now()}`;
    const res = await fetch(`${baseURL}/api/agents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: agentName, config: extractOnlyVariableAgent }),
    });
    expect(res.ok).toBe(true);

    await page.goto("/");
    const agentBtn = page.getByRole("button", { name: agentName });
    await expect(agentBtn).toBeVisible({ timeout: 10000 });
    await agentBtn.click();

    await page.getByRole("button", { name: "Chat with Agent" }).click();

    await expect(page.getByText("Chat Variables")).toBeVisible();
    await expect(page.getByLabel("available_color")).toBeVisible();

    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByText("Chat Variables")).toBeHidden();
    await expect(page.locator(".chat-panel")).toBeHidden();
  });
});
