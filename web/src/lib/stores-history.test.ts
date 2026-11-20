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
    startRun: vi.fn(() =>
      Promise.resolve({ id: "new", agent_id: "a1", started_at: "2026-11-01T00:00:00+00:00" })
    ),
    getWebSocketUrl: (path: string) => `ws://test${path}`,
  },
}));

import { api } from "./api";
import {
  applyHash,
  clearCurrentRun,
  currentRunId,
  currentRunWithResults,
  currentView,
  forgetRun,
  initStores,
  now,
  selectResult,
  selectRun,
  selectedResultId,
  startRun,
} from "./stores";
import type { RunWithResults } from "./types";

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

  it("Back to a deleted agent replaces the entry with the import page", async () => {
    const start = window.history.length;
    window.history.replaceState(null, "", "#/agent/gone/tests");

    await applyHash();
    await flush();

    expect(get(currentView)).toBe("import");
    expect(window.location.hash).toBe("#/import");
    expect(window.history.length).toBe(start);
  });

  it("a slow earlier run load cannot overwrite a newer navigation", async () => {
    let resolveSlow!: (run: RunWithResults) => void;
    const getRun = api.getRun as ReturnType<typeof vi.fn>;
    getRun.mockImplementationOnce(
      () => new Promise<RunWithResults>((resolve) => (resolveSlow = resolve))
    );
    currentView.set("runs");
    clearCurrentRun();
    await flush();

    window.history.replaceState(null, "", "#/agent/a1/runs/slow");
    const first = applyHash();
    window.history.replaceState(null, "", "#/agent/a1/runs/fast");
    await applyHash();
    resolveSlow({ id: "slow", agent_id: "a1", started_at: "", completed_at: "", results: [] });
    await first;
    await flush();

    expect(get(currentRunId)).toBe("fast");
    expect(get(currentRunWithResults)?.id).toBe("fast");
    expect(window.location.hash).toBe("#/agent/a1/runs/fast");
  });

  it("a click during a slow restore still pushes", async () => {
    let resolveSlow!: (run: RunWithResults) => void;
    (api.getRun as ReturnType<typeof vi.fn>).mockImplementationOnce(
      () => new Promise<RunWithResults>((resolve) => (resolveSlow = resolve))
    );
    window.history.replaceState(null, "", "#/agent/a1/runs/r9");
    const restore = applyHash();
    await flush();
    const start = window.history.length;

    currentView.set("metrics");
    await flush();

    expect(window.history.length).toBe(start + 1);
    resolveSlow({ id: "r9", agent_id: "a1", started_at: "", completed_at: "", results: [] });
    await restore;
  });

  it("starting a run adds one entry and Back returns to the tests view", async () => {
    currentView.set("tests");
    await flush();
    const start = window.history.length;

    currentView.set("runs");
    await startRun("a1");
    await flush();

    expect(window.history.length).toBe(start + 1);
    expect(window.location.hash).toBe("#/agent/a1/runs/new");
    await goBack();
    expect(get(currentView)).toBe("tests");
  });

  it("changing run clears the previous run's selected result", async () => {
    await selectRun("a1", "r4");
    selectResult("res-of-r4");
    await flush();

    await selectRun("a1", "r5");
    await flush();

    expect(get(selectedResultId)).toBeNull();
    expect(window.location.hash).toBe("#/agent/a1/runs/r5");
  });

  it("forgetting the open run returns to the list without a new entry", async () => {
    await selectRun("a1", "r6");
    await flush();
    const start = window.history.length;

    forgetRun("r6");
    await flush();

    expect(get(currentRunId)).toBeNull();
    expect(window.location.hash).toBe("#/agent/a1/runs");
    expect(window.history.length).toBe(start);
  });

  it("the clock reads the current time when a view subscribes", () => {
    vi.useFakeTimers();
    try {
      vi.setSystemTime(Date.UTC(2030, 0, 1));
      expect(get(now)).toBe(Date.UTC(2030, 0, 1));
    } finally {
      vi.useRealTimers();
    }
  });
});
