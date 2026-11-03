import { describe, it, expect, beforeEach, vi } from "vitest";
import { get } from "svelte/store";

vi.mock("./api", () => ({
  api: {
    listRunsForAgent: vi.fn(),
    countRunsForAgent: vi.fn(),
  },
}));

import { api } from "./api";
import { loadOlderRuns, loadRunHistory, runHistory, runTotal, RUN_PAGE_SIZE } from "./stores";
import type { RunRecord } from "./types";

function run(id: string): RunRecord {
  return { id, agent_id: "a1", started_at: "2026-11-01T00:00:00", completed_at: null };
}

const listRuns = api.listRunsForAgent as ReturnType<typeof vi.fn>;
const countRuns = api.countRunsForAgent as ReturnType<typeof vi.fn>;

describe("run history paging", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    runHistory.set([]);
    runTotal.set(0);
  });

  it("loads the newest page and the true total", async () => {
    listRuns.mockResolvedValue([run("r3"), run("r2")]);
    countRuns.mockResolvedValue({ total: 60 });

    await loadRunHistory("a1");

    expect(listRuns).toHaveBeenCalledWith("a1", RUN_PAGE_SIZE);
    expect(get(runHistory).map((r) => r.id)).toEqual(["r3", "r2"]);
    expect(get(runTotal)).toBe(60);
  });

  it("appends older runs after the ones already loaded", async () => {
    runHistory.set([run("r3"), run("r2")]);
    listRuns.mockResolvedValue([run("r1")]);

    await loadOlderRuns("a1");

    expect(listRuns).toHaveBeenCalledWith("a1", RUN_PAGE_SIZE, 2);
    expect(get(runHistory).map((r) => r.id)).toEqual(["r3", "r2", "r1"]);
  });

  it("skips runs that are already in the list", async () => {
    runHistory.set([run("r3"), run("r2")]);
    listRuns.mockResolvedValue([run("r2"), run("r1")]);

    await loadOlderRuns("a1");

    expect(get(runHistory).map((r) => r.id)).toEqual(["r3", "r2", "r1"]);
  });
});
