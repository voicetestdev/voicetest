import { writable, derived, get } from "svelte/store";
import type {
  AgentGraph,
  AgentRecord,
  RetryInfo,
  RunRecord,
  RunResultRecord,
  RunWithResults,
  TestCase,
  TestCaseRecord,
  TestRun,
  Settings,
} from "./types";
import { api } from "./api";

export const agents = writable<AgentRecord[]>([]);
export const currentAgentId = writable<string | null>(null);
export const agentGraph = writable<AgentGraph | null>(null);
export const testCaseRecords = writable<TestCaseRecord[]>([]);
export const testCases = writable<TestCase[]>([]);
export const currentRun = writable<TestRun | null>(null);
export const settings = writable<Settings | null>(null);

export const isRunning = writable(false);
export const selectedTestId = writable<string | null>(null);

export const runHistory = writable<RunRecord[]>([]);
export const currentRunId = writable<string | null>(null);
export const currentRunWithResults = writable<RunWithResults | null>(null);
export const runWebSocket = writable<WebSocket | null>(null);

// Track retry status per result_id
export const retryStatus = writable<Map<string, RetryInfo>>(new Map());

// Persist expandedRuns to localStorage
function loadExpandedRuns(): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem("expandedRuns") === "true";
}
export const expandedRuns = writable(loadExpandedRuns());
if (typeof window !== "undefined") {
  expandedRuns.subscribe((v) => localStorage.setItem("expandedRuns", String(v)));
}

export type NavView = "config" | "tests" | "runs" | "metrics" | "settings" | "import";
export const currentView = writable<NavView>("import");

// Persist expandedAgents to localStorage
function loadExpandedAgents(): Set<string> {
  if (typeof window === "undefined") return new Set();
  const stored = localStorage.getItem("expandedAgents");
  if (!stored) return new Set();
  try {
    return new Set(JSON.parse(stored));
  } catch {
    return new Set();
  }
}
export const expandedAgents = writable<Set<string>>(loadExpandedAgents());
if (typeof window !== "undefined") {
  expandedAgents.subscribe((v) => localStorage.setItem("expandedAgents", JSON.stringify([...v])));
}

function parseHash(): { agentId: string | null; view: NavView; runId: string | null } {
  if (typeof window === "undefined") return { agentId: null, view: "import", runId: null };
  const hash = window.location.hash.slice(1);
  if (!hash) return { agentId: null, view: "import", runId: null };

  const parts = hash.split("/").filter(Boolean);
  if (parts[0] === "settings") {
    return { agentId: null, view: "settings", runId: null };
  }
  if (parts[0] === "import") {
    return { agentId: null, view: "import", runId: null };
  }
  if (parts[0] === "agent" && parts[1]) {
    const view = (parts[2] as NavView) || "config";
    const runId = view === "runs" && parts[3] ? parts[3] : null;
    return { agentId: parts[1], view, runId };
  }
  return { agentId: null, view: "import", runId: null };
}

function updateHash(agentId: string | null, view: NavView, runId: string | null): void {
  if (typeof window === "undefined") return;
  let hash = "";
  if (view === "settings") {
    hash = "#/settings";
  } else if (view === "import" || !agentId) {
    hash = "#/import";
  } else if (view === "runs" && runId) {
    hash = `#/agent/${agentId}/runs/${runId}`;
  } else {
    hash = `#/agent/${agentId}/${view}`;
  }
  if (window.location.hash !== hash) {
    window.history.replaceState(null, "", hash);
  }
}

let currentAgentIdValue: string | null = null;
let currentViewValue: NavView = "import";
let currentRunIdValue: string | null = null;
// Disabled initially - subscriptions fire immediately with default values which would corrupt the hash
let hashUpdateEnabled = false;

currentAgentId.subscribe((v) => {
  currentAgentIdValue = v;
  if (hashUpdateEnabled) {
    updateHash(v, currentViewValue, currentRunIdValue);
  }
});

currentView.subscribe((v) => {
  currentViewValue = v;
  if (hashUpdateEnabled) {
    updateHash(currentAgentIdValue, v, currentRunIdValue);
  }
});

currentRunId.subscribe((v) => {
  currentRunIdValue = v;
  if (hashUpdateEnabled) {
    updateHash(currentAgentIdValue, currentViewValue, v);
  }
});

if (typeof window !== "undefined") {
  window.addEventListener("hashchange", async () => {
    const { agentId, view, runId } = parseHash();
    if (view === "settings") {
      currentView.set("settings");
      currentAgentId.set(null);
    } else if (agentId && agentId !== currentAgentIdValue) {
      await selectAgent(agentId, view, runId);
    } else if (view !== currentViewValue) {
      currentView.set(view);
      if (view === "runs" && runId) {
        await loadRun(runId);
      }
    } else if (view === "runs" && runId && runId !== currentRunIdValue) {
      await loadRun(runId);
    }
  });
}

export const currentAgent = derived(
  [agents, currentAgentId],
  ([$agents, $id]) => $agents.find((a) => a.id === $id) ?? null
);

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

function parseTestCaseRecord(record: TestCaseRecord): TestCase {
  return {
    name: record.name,
    user_prompt: record.user_prompt,
    metrics: record.metrics ? JSON.parse(record.metrics) : [],
    dynamic_variables: record.dynamic_variables
      ? JSON.parse(record.dynamic_variables)
      : {},
    tool_mocks: record.tool_mocks ? JSON.parse(record.tool_mocks) : [],
    type: record.type || "llm",
    llm_model: record.llm_model ?? undefined,
    includes: record.includes ? JSON.parse(record.includes) : [],
    excludes: record.excludes ? JSON.parse(record.excludes) : [],
    patterns: record.patterns ? JSON.parse(record.patterns) : [],
  };
}

export async function loadAgents(): Promise<void> {
  const agentList = await api.listAgents();
  agents.set(agentList);
}

export async function selectAgent(agentId: string, view: NavView = "config", runId: string | null = null): Promise<void> {
  // Batch the state updates to prevent intermediate hash corruption
  hashUpdateEnabled = false;
  currentAgentId.set(agentId);
  currentView.set(view);
  if (runId) {
    currentRunId.set(runId);
  }
  hashUpdateEnabled = true;
  // Now update hash once with all correct values
  updateHash(agentId, view, runId);

  expandedAgents.update((set) => {
    set.add(agentId);
    return new Set(set);
  });

  const [graph, records, runs] = await Promise.all([
    api.getAgentGraph(agentId),
    api.listTestsForAgent(agentId),
    api.listRunsForAgent(agentId),
  ]);

  agentGraph.set(graph);
  testCaseRecords.set(records);
  testCases.set(records.map(parseTestCaseRecord));
  runHistory.set(runs);

  // Load specific run or first run when viewing runs
  if (view === "runs") {
    if (runId) {
      await loadRun(runId);
    } else if (runs.length > 0) {
      await loadRun(runs[0].id);
    }
  }
}

export function toggleAgentExpanded(agentId: string): void {
  expandedAgents.update((set) => {
    if (set.has(agentId)) {
      set.delete(agentId);
    } else {
      set.add(agentId);
    }
    return new Set(set);
  });
}

export async function loadSettings(): Promise<void> {
  const s = await api.getSettings();
  settings.set(s);
}

export async function initStores(): Promise<void> {
  await Promise.all([loadAgents(), loadSettings()]);

  const agentList = get(agents);

  const { agentId, view, runId } = parseHash();

  if (view === "settings") {
    currentView.set("settings");
  } else if (view === "import") {
    currentView.set("import");
  } else if (agentId && agentList.some((a) => a.id === agentId)) {
    await selectAgent(agentId, view, runId);
  } else if (agentList.length > 0) {
    await selectAgent(agentList[0].id, "config");
  } else {
    currentView.set("import");
  }

  // Enable hash updates now that initialization is complete
  hashUpdateEnabled = true;
}

export async function loadRunHistory(agentId: string): Promise<void> {
  const runs = await api.listRunsForAgent(agentId);
  runHistory.set(runs);
}

export async function selectRun(agentId: string, runId: string): Promise<void> {
  // If same agent, just load the run without refetching agent data
  if (currentAgentIdValue === agentId) {
    // Batch updates to prevent flash of old run
    hashUpdateEnabled = false;
    currentView.set("runs");
    currentRunId.set(runId);
    hashUpdateEnabled = true;
    updateHash(agentId, "runs", runId);
    await loadRun(runId);
  } else {
    await selectAgent(agentId, "runs", runId);
  }
}

export async function loadRun(runId: string): Promise<void> {
  disconnectRunWebSocket();
  const run = await api.getRun(runId);
  currentRunWithResults.set(run);
  currentRunId.set(runId);
  // Connect WebSocket if run is still active
  if (!run.completed_at) {
    isRunning.set(true);
    connectRunWebSocket(runId);
  } else {
    isRunning.set(false);
  }
}

export async function startRun(agentId: string, testIds?: string[]): Promise<string> {
  disconnectRunWebSocket();
  isRunning.set(true);
  currentRunWithResults.set(null);

  const response = await api.startRun(agentId, testIds);
  currentRunId.set(response.id);

  // Add new run to history immediately so it appears in sidebar
  const newRun: RunRecord = {
    id: response.id,
    agent_id: response.agent_id,
    started_at: response.started_at,
    completed_at: null,
  };
  runHistory.update((runs) => [newRun, ...runs]);

  // Set initial empty results so UI shows the run immediately
  currentRunWithResults.set({
    ...newRun,
    results: [],
  });

  // Expand runs in sidebar
  expandedRuns.set(true);

  connectRunWebSocket(response.id);

  return response.id;
}

let pollInterval: ReturnType<typeof setInterval> | null = null;

export function connectRunWebSocket(runId: string): void {
  disconnectRunWebSocket();

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/api/runs/${runId}/ws`;
  const ws = new WebSocket(wsUrl);

  // Poll API as fallback for missed WebSocket messages
  pollInterval = setInterval(async () => {
    const current = get(currentRunWithResults);
    if (current && current.id === runId && !current.completed_at) {
      const fresh = await api.getRun(runId);
      // Merge: keep running results from current that aren't in server state
      const serverResultIds = new Set(fresh.results.map((r: RunWithResults["results"][0]) => r.id));
      const runningResultsToKeep = current.results.filter(
        (r) => r.status === "running" && !serverResultIds.has(r.id)
      );
      currentRunWithResults.set({
        ...fresh,
        results: [...fresh.results, ...runningResultsToKeep],
      });
    }
  }, 3000);

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.type === "state" && data.run) {
      // Merge results to avoid losing running tests that may not be in DB yet
      currentRunWithResults.update((current) => {
        if (!current || current.id !== data.run.id) {
          return data.run;
        }
        // Merge: keep running results from current that aren't in server state
        const serverResultIds = new Set(data.run.results.map((r: RunResultRecord) => r.id));
        const runningResultsToKeep = current.results.filter(
          (r) => r.status === "running" && !serverResultIds.has(r.id)
        );
        return {
          ...data.run,
          results: [...data.run.results, ...runningResultsToKeep],
        };
      });
    } else if (data.type === "test_started") {
      // Add running result to the list
      currentRunWithResults.update((run) => {
        // Create run structure if not yet set (race condition fix)
        if (!run) {
          run = {
            id: runId,
            agent_id: "",
            started_at: new Date().toISOString(),
            completed_at: null,
            results: [],
          };
        }
        // Ensure we're updating the correct run
        if (run.id !== runId) return run;
        const exists = run.results.some((r) => r.id === data.result_id);
        if (exists) return run;
        const newResult: RunResultRecord = {
          id: data.result_id,
          run_id: runId,
          test_case_id: data.test_case_id || "",
          test_name: data.test_name,
          status: "running",
          duration_ms: null,
          turn_count: null,
          end_reason: null,
          error_message: null,
          transcript_json: "[]",
          metrics_json: null,
          nodes_visited: null,
          tools_called: null,
          models_used: null,
          created_at: new Date().toISOString(),
        };
        return {
          ...run,
          results: [...run.results, newResult],
        };
      });
    } else if (data.type === "transcript_update") {
      currentRunWithResults.update((run) => {
        if (!run || run.id !== runId) return run;
        return {
          ...run,
          results: run.results.map((r) =>
            r.id === data.result_id
              ? { ...r, transcript_json: JSON.stringify(data.transcript) }
              : r
          ),
        };
      });
    } else if (data.type === "test_completed" || data.type === "test_error" || data.type === "test_cancelled") {
      // Clear retry status only on success or cancel (keep on error for context)
      if (data.type !== "test_error") {
        retryStatus.update((map) => {
          const newMap = new Map(map);
          newMap.delete(data.result_id);
          return newMap;
        });
      }
      // Refresh full state to get complete result data
      api.getRun(runId).then((fresh) => {
        currentRunWithResults.update((current) => {
          if (!current || current.id !== runId) return current;
          // Merge: keep running results from current that aren't in server state
          const serverResultIds = new Set(fresh.results.map((r: RunWithResults["results"][0]) => r.id));
          const runningResultsToKeep = current.results.filter(
            (r) => r.status === "running" && !serverResultIds.has(r.id)
          );
          return {
            ...fresh,
            results: [...fresh.results, ...runningResultsToKeep],
          };
        });
      });
    } else if (data.type === "retry_error") {
      // Track retry status for display
      retryStatus.update((map) => {
        const newMap = new Map(map);
        newMap.set(data.result_id, {
          result_id: data.result_id,
          error_type: data.error_type,
          message: data.message,
          attempt: data.attempt,
          max_attempts: data.max_attempts,
          retry_after: data.retry_after,
        });
        return newMap;
      });
    } else if (data.type === "run_completed") {
      isRunning.set(false);
      // Clear retry status for this run
      retryStatus.set(new Map());
      // Update the run to mark it as completed
      currentRunWithResults.update((run) => {
        if (!run) return run;
        return {
          ...run,
          completed_at: new Date().toISOString(),
        };
      });
      const agentId = get(currentAgentId);
      if (agentId) {
        loadRunHistory(agentId);
      }
      disconnectRunWebSocket();
    }
  };

  ws.onclose = () => {
    runWebSocket.set(null);
  };

  runWebSocket.set(ws);
}

export function disconnectRunWebSocket(): void {
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
  const ws = get(runWebSocket);
  if (ws) {
    ws.close();
    runWebSocket.set(null);
  }
}

export function cancelTest(resultId: string): void {
  const ws = get(runWebSocket);
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "cancel_test", result_id: resultId }));
  }
}

export function cancelRun(): void {
  const ws = get(runWebSocket);
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "cancel_run" }));
  }
}
