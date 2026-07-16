import { describe, it, expect, beforeEach, vi } from "vitest";
import { get } from "svelte/store";

vi.mock("./api", () => ({
  api: {
    getAgentGraph: vi.fn(),
    listTestsForAgent: vi.fn(),
    listRunsForAgent: vi.fn(),
  },
}));

import { api } from "./api";
import {
  selectAgent,
  agentGraph,
  agentGraphError,
  runHistory,
  currentAgentId,
} from "./stores";

const graph = {
  entry_node_id: "n",
  nodes: {},
  source_type: "test",
  source_metadata: {},
};

describe("selectAgent when a linked file is missing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    agentGraph.set(null);
    agentGraphError.set(null);
    runHistory.set([]);
    currentAgentId.set(null);
  });

  it("degrades instead of throwing when the graph fetch fails", async () => {
    (api.getAgentGraph as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("File not found: /moved/agent.json"),
    );
    (api.listTestsForAgent as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (api.listRunsForAgent as ReturnType<typeof vi.fn>).mockResolvedValue([{ id: "run-1" }]);

    await selectAgent("agent-missing", "config");

    expect(get(agentGraph)).toBeNull();
    expect(get(agentGraphError)).toContain("File not found");
    expect(get(runHistory)).toHaveLength(1);
  });

  it("clears a stale graph error on a successful load", async () => {
    agentGraphError.set("previous failure");
    (api.getAgentGraph as ReturnType<typeof vi.fn>).mockResolvedValue(graph);
    (api.listTestsForAgent as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (api.listRunsForAgent as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    await selectAgent("agent-ok", "config");

    expect(get(agentGraphError)).toBeNull();
    expect(get(agentGraph)).not.toBeNull();
  });
});
