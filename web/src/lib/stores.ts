import { writable, derived } from "svelte/store";
import type { AgentGraph, TestCase, TestRun, Settings } from "./types";

export const agentGraph = writable<AgentGraph | null>(null);
export const testCases = writable<TestCase[]>([]);
export const currentRun = writable<TestRun | null>(null);
export const settings = writable<Settings | null>(null);

export const isRunning = writable(false);
export const selectedTestId = writable<string | null>(null);
export const currentView = writable<"agents" | "tests" | "runs" | "settings">("agents");

export const selectedResult = derived(
  [currentRun, selectedTestId],
  ([$run, $id]) => $run?.results.find((r) => r.test_id === $id) ?? null
);

export const runSummary = derived(currentRun, ($run) => {
  if (!$run) return null;
  return {
    total: $run.results.length,
    passed: $run.passed_count,
    failed: $run.failed_count,
  };
});
