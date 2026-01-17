import type {
  AgentGraph,
  ExporterInfo,
  ImporterInfo,
  MetricResult,
  Message,
  RunOptions,
  Settings,
  TestCase,
  TestResult,
  TestRun,
} from "./types";

const BASE_URL = "/api";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

export const api = {
  health: () => get<{ status: string }>("/health"),

  listImporters: () => get<ImporterInfo[]>("/importers"),

  listExporters: () => get<ExporterInfo[]>("/exporters"),

  importAgent: (config: unknown, source?: string) =>
    post<AgentGraph>("/agents/import", { config, source }),

  exportAgent: (graph: AgentGraph, format: string) =>
    post<{ content: string; format: string }>("/agents/export", {
      graph,
      format,
    }),

  runSingleTest: (
    graph: AgentGraph,
    testCase: TestCase,
    options?: Partial<RunOptions>
  ) => post<TestResult>("/runs/single", { graph, test_case: testCase, options }),

  runTests: (
    graph: AgentGraph,
    testCases: TestCase[],
    options?: Partial<RunOptions>
  ) => post<TestRun>("/runs", { graph, test_cases: testCases, options }),

  evaluate: (transcript: Message[], metrics: string[]) =>
    post<MetricResult[]>("/evaluate", { transcript, metrics }),

  getSettings: () => get<Settings>("/settings"),

  updateSettings: (settings: Settings) => put<Settings>("/settings", settings),
};
