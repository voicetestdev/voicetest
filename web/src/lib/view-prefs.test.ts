import { describe, it, expect, beforeEach, vi } from "vitest";
import { get } from "svelte/store";

vi.mock("./api", () => ({ api: {} }));

async function loadStoresWith(saved: string | null) {
  Object.defineProperty(window, "localStorage", {
    value: { getItem: vi.fn().mockReturnValue(saved), setItem: vi.fn() },
    writable: true,
  });
  vi.resetModules();
  return import("./stores");
}

describe("testSort", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("restores a saved sort on load", async () => {
    const { testSort } = await loadStoresWith(JSON.stringify({ column: "name", direction: "desc" }));

    expect(get(testSort)).toEqual({ column: "name", direction: "desc" });
  });

  it("falls back to the default for missing or invalid values", async () => {
    for (const saved of [null, "not json", JSON.stringify({ column: "bogus", direction: "asc" })]) {
      const { testSort } = await loadStoresWith(saved);

      expect(get(testSort)).toEqual({ column: "index", direction: "asc" });
    }
  });
});

describe("runConcurrency", () => {
  it("restores saved per-agent levels and drops invalid ones", async () => {
    const { runConcurrency } = await loadStoresWith(
      JSON.stringify({ "agent-1": 4, "agent-2": 3, "agent-3": "8" }),
    );

    expect(get(runConcurrency)).toEqual({ "agent-1": 4 });
  });

  it("defaults an agent without a saved level to 1", async () => {
    const { concurrencyFor } = await loadStoresWith(null);

    expect(concurrencyFor("agent-1", {})).toBe(1);
    expect(concurrencyFor(null, { "agent-1": 4 })).toBe(1);
    expect(concurrencyFor("agent-1", { "agent-1": 4 })).toBe(4);
  });
});
