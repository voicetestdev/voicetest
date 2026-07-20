import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";

vi.mock("../lib/api", () => ({
  api: {
    deleteAgent: vi.fn(() => Promise.resolve()),
    getSyncStatus: vi.fn(() => Promise.resolve(null)),
    listAgents: vi.fn(() => Promise.resolve([])),
  },
}));

import AgentView from "./AgentView.svelte";
import { api } from "../lib/api";
import {
  agents,
  currentAgentId,
  agentGraph,
  agentGraphError,
  agentGraphLoading,
} from "../lib/stores";

describe("AgentView with an unavailable graph", () => {
  beforeEach(() => {
    vi.mocked(api.getSyncStatus).mockClear();
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
    agentGraphLoading.set(false);
  });

  afterEach(() => {
    cleanup();
    agents.set([]);
    currentAgentId.set(null);
    agentGraph.set(null);
    agentGraphError.set(null);
    agentGraphLoading.set(false);
  });

  it("renders a degraded view that still exposes Delete Agent", () => {
    render(AgentView);

    expect(screen.getByText("Pharmacy Agent")).toBeTruthy();
    expect(screen.getByText("Graph unavailable")).toBeTruthy();
    expect(screen.getByText("Delete Agent")).toBeTruthy();
    expect(screen.getAllByText(/\/moved\/agent\.json/).length).toBeGreaterThan(0);
  });

  it("shows the actual error, not only the moved/deleted hint, for a linked agent", () => {
    render(AgentView);

    expect(screen.getByText("File not found: /moved/agent.json")).toBeTruthy();
  });

  it("shows a loading state, not 'Graph unavailable', while the graph loads", () => {
    agentGraphError.set(null);
    agentGraphLoading.set(true);
    render(AgentView);

    expect(screen.queryByText("Graph unavailable")).toBeNull();
    expect(screen.getByText(/Loading/)).toBeTruthy();
  });

  it("clears agentGraphError when the agent is deleted", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(AgentView);

    await fireEvent.click(screen.getByText("Delete Agent"));

    await waitFor(() => expect(get(agentGraphError)).toBeNull());
  });

  it("does not fetch sync status for a degraded agent (no graph)", async () => {
    render(AgentView);
    await new Promise((r) => setTimeout(r, 0));

    expect(vi.mocked(api.getSyncStatus)).not.toHaveBeenCalled();
  });
});
