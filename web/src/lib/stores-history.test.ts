import { describe, it, expect, beforeAll, beforeEach, vi } from "vitest";
import { get } from "svelte/store";

vi.mock("./api", () => ({
  api: {
    listAgents: vi.fn(() => Promise.resolve([{ id: "a1", name: "Agent" }])),
    getSettings: vi.fn(() => Promise.resolve({})),
    listImporters: vi.fn(() => Promise.resolve([])),
    getAgentGraph: vi.fn(() =>
      Promise.resolve({ entry_node_id: "n", nodes: {}, source_type: "test", source_metadata: {} })
    ),
    listTestsForAgent: vi.fn(() => Promise.resolve([])),
    listRunsForAgent: vi.fn(() => Promise.resolve([])),
    countRunsForAgent: vi.fn(() => Promise.resolve({ total: 0 })),
    getRun: vi.fn((id: string) =>
      Promise.resolve({
        id,
        agent_id: "a1",
        started_at: "2026-11-01T00:00:00+00:00",
        completed_at: "2026-11-01T00:01:00+00:00",
        results: [],
      })
    ),
    getWebSocketUrl: (path: string) => `ws://test${path}`,
  },
}));

import { api } from "./api";
import {
  applyHash,
  clearCurrentRun,
  currentRunId,
  currentView,
  initStores,
  selectResult,
  selectRun,
  selectedResultId,
} from "./stores";

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

async function goBack(): Promise<void> {
  const done = new Promise((resolve) => window.addEventListener("popstate", resolve, { once: true }));
  window.history.back();
  await done;
  await applyHash();
  await flush();
}

describe("browser history", () => {
  beforeAll(async () => {
    vi.stubGlobal("WebSocket", class {
      close() {}
    });
    window.history.replaceState(null, "", "#/agent/a1/config");
    await initStores();
    await flush();
  });

  beforeEach(async () => {
    currentView.set("config");
    await flush();
  });

  it("does not add an entry while restoring the initial location", () => {
    expect(window.location.hash).toBe("#/agent/a1/config");
  });

  it("pushes one entry per view change and Back restores the previous view", async () => {
    const start = window.history.length;

    currentView.set("tests");
    await flush();
    currentView.set("metrics");
    await flush();

    expect(window.history.length).toBe(start + 2);
    await goBack();
    expect(get(currentView)).toBe("tests");
    expect(window.location.hash).toBe("#/agent/a1/tests");
  });

  it("coalesces changes made in the same tick into one entry", async () => {
    const start = window.history.length;

    currentView.set("runs");
    clearCurrentRun();
    await flush();

    expect(window.history.length).toBe(start + 1);
    expect(window.location.hash).toBe("#/agent/a1/runs");
  });

  it("Back from a run detail returns to the runs list", async () => {
    currentView.set("runs");
    clearCurrentRun();
    await flush();
    await selectRun("a1", "r1");
    await flush();
    expect(window.location.hash).toBe("#/agent/a1/runs/r1");

    await goBack();

    expect(get(currentRunId)).toBeNull();
    expect(window.location.hash).toBe("#/agent/a1/runs");
  });

  it("pushes user-picked results but only replaces automatic ones", async () => {
    await selectRun("a1", "r2");
    await flush();
    const start = window.history.length;

    selectedResultId.set("auto");
    await flush();
    expect(window.history.length).toBe(start);
    expect(window.location.hash).toBe("#/agent/a1/runs/r2/auto");

    selectResult("picked");
    await flush();
    expect(window.history.length).toBe(start + 1);

    await goBack();
    expect(get(selectedResultId)).toBe("auto");
  });

  it("restoring a location never pushes", async () => {
    currentView.set("tests");
    await flush();
    const start = window.history.length;
    window.history.replaceState(null, "", "#/agent/a1/runs/r3/res1");

    await applyHash();
    await flush();

    expect(window.history.length).toBe(start);
    expect(api.getRun).toHaveBeenCalledWith("r3");
    expect(window.location.hash).toBe("#/agent/a1/runs/r3/res1");
  });
});
