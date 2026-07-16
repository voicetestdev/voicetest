import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/svelte";

vi.mock("../lib/api", () => ({
  api: {
    deleteAgent: () => Promise.resolve(),
    getSyncStatus: () => Promise.resolve(null),
  },
}));

import AgentView from "./AgentView.svelte";
import { agents, currentAgentId, agentGraph, agentGraphError } from "../lib/stores";

describe("AgentView with an unavailable graph", () => {
  beforeEach(() => {
    agents.set([
      {
        id: "a1",
        name: "Pharmacy Agent",
        source_type: "retell",
        source_path: "/moved/agent.json",
      } as never,
    ]);
    currentAgentId.set("a1");
    agentGraph.set(null);
    agentGraphError.set("File not found: /moved/agent.json");
  });

  afterEach(() => {
    cleanup();
    agents.set([]);
    currentAgentId.set(null);
    agentGraph.set(null);
    agentGraphError.set(null);
  });

  it("renders a degraded view that still exposes Delete Agent", () => {
    render(AgentView);

    expect(screen.getByText("Pharmacy Agent")).toBeTruthy();
    expect(screen.getByText("Graph unavailable")).toBeTruthy();
    expect(screen.getByText("Delete Agent")).toBeTruthy();
    expect(screen.getByText(/\/moved\/agent\.json/)).toBeTruthy();
  });
});
