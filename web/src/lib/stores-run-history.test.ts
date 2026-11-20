import { describe, it, expect, beforeEach, vi } from "vitest";
import { get } from "svelte/store";

vi.mock("./api", () => ({
  api: {
    listRunsForAgent: vi.fn(),
    countRunsForAgent: vi.fn(),
    getWebSocketUrl: (path: string) => `ws://test${path}`,
  },
}));

import { api } from "./api";
import {
  currentAgentId,
  loadOlderRuns,
  loadRunHistory,
  refreshRunHistory,
  runHistory,
  runTotal,
  RUN_PAGE_SIZE,
} from "./stores";
import type { RunRecord } from "./types";

function run(id: string, startedAt = "2026-11-01T00:00:00+00:00"): RunRecord {
  return { id, agent_id: "a1", started_at: startedAt, completed_at: null };
}

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }
  close() {}
  emit(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
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

describe("run history push feed", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("WebSocket", FakeWebSocket);
    FakeWebSocket.instances = [];
    currentAgentId.set(null);
    runHistory.set([]);
    runTotal.set(0);
  });

  it("subscribes to the selected agent's runs feed", () => {
    currentAgentId.set("a1");

    expect(FakeWebSocket.instances.map((ws) => ws.url)).toEqual(["ws://test/agents/a1/runs/ws"]);
  });

  it("removes a deleted run at once and refetches the true total", async () => {
    vi.useFakeTimers();
    try {
      currentAgentId.set("a1");
      runHistory.set([run("r2"), run("r1")]);
      listRuns.mockResolvedValue([run("r1")]);
      countRuns.mockResolvedValue({ total: 1 });

      FakeWebSocket.instances[0].emit({ type: "run_deleted", run_id: "r2" });
      expect(get(runHistory).map((r) => r.id)).toEqual(["r1"]);

      await vi.advanceTimersByTimeAsync(400);
      expect(get(runTotal)).toBe(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not refetch on the first subscribe, only on reconnect", async () => {
    vi.useFakeTimers();
    try {
      currentAgentId.set("a1");
      FakeWebSocket.instances[0].emit({ type: "subscribed" });
      await vi.advanceTimersByTimeAsync(400);
      expect(listRuns).not.toHaveBeenCalled();

      listRuns.mockResolvedValue([]);
      countRuns.mockResolvedValue({ total: 0 });
      FakeWebSocket.instances[0].onclose?.();
      await vi.advanceTimersByTimeAsync(1000);
      FakeWebSocket.instances[1].emit({ type: "subscribed" });
      await vi.advanceTimersByTimeAsync(400);
      expect(listRuns).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("backs off reconnects exponentially", async () => {
    vi.useFakeTimers();
    try {
      currentAgentId.set("a1");
      FakeWebSocket.instances[0].onclose?.();
      await vi.advanceTimersByTimeAsync(1000);
      expect(FakeWebSocket.instances).toHaveLength(2);

      FakeWebSocket.instances[1].onclose?.();
      await vi.advanceTimersByTimeAsync(1999);
      expect(FakeWebSocket.instances).toHaveLength(2);
      await vi.advanceTimersByTimeAsync(1);
      expect(FakeWebSocket.instances).toHaveLength(3);
    } finally {
      vi.useRealTimers();
    }
  });

  it("debounces run updates into one refetch", async () => {
    vi.useFakeTimers();
    try {
      currentAgentId.set("a1");
      listRuns.mockResolvedValue([run("r1")]);
      countRuns.mockResolvedValue({ total: 1 });
      const ws = FakeWebSocket.instances[0];

      ws.emit({ type: "subscribed" });
      ws.emit({ type: "run_updated", run_id: "r1" });
      ws.emit({ type: "run_updated", run_id: "r1" });
      await vi.advanceTimersByTimeAsync(400);

      expect(listRuns).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("refresh puts new runs first and keeps older pages loaded", async () => {
    currentAgentId.set("a1");
    const page = Array.from({ length: RUN_PAGE_SIZE }, (_, i) =>
      run(`p${i}`, new Date(Date.UTC(2026, 10, 10, 12, 0, 0) - i * 60_000).toISOString())
    );
    const older = run("old", "2026-11-01T00:00:00+00:00");
    runHistory.set([...page.slice(1), older]);
    listRuns.mockResolvedValue(page);
    countRuns.mockResolvedValue({ total: RUN_PAGE_SIZE + 1 });

    await refreshRunHistory("a1");

    expect(get(runHistory).map((r) => r.id)).toEqual([...page.map((r) => r.id), "old"]);
    expect(get(runTotal)).toBe(RUN_PAGE_SIZE + 1);
  });

  it("refresh drops runs missing from a complete first page", async () => {
    currentAgentId.set("a1");
    runHistory.set([run("r2"), run("gone"), run("r1")]);
    listRuns.mockResolvedValue([run("r3"), run("r2"), run("r1")]);
    countRuns.mockResolvedValue({ total: 3 });

    await refreshRunHistory("a1");

    expect(get(runHistory).map((r) => r.id)).toEqual(["r3", "r2", "r1"]);
  });

  it("refresh ignores a response for an agent no longer selected", async () => {
    currentAgentId.set("a2");
    runHistory.set([run("r9")]);
    listRuns.mockResolvedValue([run("r1")]);
    countRuns.mockResolvedValue({ total: 1 });

    await refreshRunHistory("a1");

    expect(get(runHistory).map((r) => r.id)).toEqual(["r9"]);
  });
});
