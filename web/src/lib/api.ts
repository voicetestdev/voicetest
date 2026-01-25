import type {
  AgentGraph,
  AgentRecord,
  ExporterInfo,
  ExportToPlatformResponse,
  GalleryItem,
  ImporterInfo,
  LoadDemoResponse,
  MetricResult,
  MetricsConfig,
  Message,
  Platform,
  PlatformInfo,
  PlatformStatus,
  RemoteAgentInfo,
  RunOptions,
  RunRecord,
  RunWithResults,
  Settings,
  StartRunResponse,
  TestCase,
  TestCaseRecord,
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

async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

async function postFile<T>(path: string, file: File, source?: string): Promise<T> {
  const formData = new FormData();
  formData.append("file", file);
  if (source) {
    formData.append("source", source);
  }
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    body: formData,
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

  importAgentFile: (file: File, source?: string) =>
    postFile<AgentGraph>("/agents/import-file", file, source),

  createAgentFromFile: (file: File, name?: string, source?: string) => {
    const formData = new FormData();
    formData.append("file", file);
    if (name) formData.append("name", name);
    if (source) formData.append("source", source);
    return fetch(`${BASE_URL}/agents/upload`, {
      method: "POST",
      body: formData,
    }).then(async (res) => {
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || res.statusText);
      }
      return res.json() as Promise<AgentRecord>;
    });
  },

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

  getDefaultSettings: () => get<Settings>("/settings/defaults"),

  updateSettings: (settings: Settings) => put<Settings>("/settings", settings),

  listAgents: () => get<AgentRecord[]>("/agents"),

  getAgent: (id: string) => get<AgentRecord>(`/agents/${id}`),

  getAgentGraph: (id: string) => get<AgentGraph>(`/agents/${id}/graph`),

  createAgent: (name: string, config: unknown, source?: string) =>
    post<AgentRecord>("/agents", { name, config, source }),

  createAgentFromPath: (name: string, path: string, source?: string) =>
    post<AgentRecord>("/agents", { name, path, source }),

  updateAgent: (id: string, name: string) =>
    put<AgentRecord>(`/agents/${id}`, { name }),

  deleteAgent: (id: string) => del<{ status: string; id: string }>(`/agents/${id}`),

  listTestsForAgent: (agentId: string) =>
    get<TestCaseRecord[]>(`/agents/${agentId}/tests`),

  createTestCase: (agentId: string, testCase: Partial<TestCase>) =>
    post<TestCaseRecord>(`/agents/${agentId}/tests`, testCase),

  updateTestCase: (testId: string, testCase: Partial<TestCase>) =>
    put<TestCaseRecord>(`/tests/${testId}`, testCase),

  deleteTestCase: (testId: string) =>
    del<{ status: string; id: string }>(`/tests/${testId}`),

  exportTests: (agentId: string, format: string, testIds?: string[]) =>
    post<unknown[]>(`/agents/${agentId}/tests/export`, { format, test_ids: testIds }),

  listGallery: () => get<GalleryItem[]>("/gallery"),

  listRunsForAgent: (agentId: string, limit = 50) =>
    get<RunRecord[]>(`/agents/${agentId}/runs?limit=${limit}`),

  getRun: (runId: string) => get<RunWithResults>(`/runs/${runId}`),

  deleteRun: (runId: string) => del<{ status: string; id: string }>(`/runs/${runId}`),

  startRun: (agentId: string, testIds?: string[], options?: Partial<RunOptions>) =>
    post<StartRunResponse>(`/agents/${agentId}/runs`, { test_ids: testIds, options }),

  getMetricsConfig: (agentId: string) =>
    get<MetricsConfig>(`/agents/${agentId}/metrics-config`),

  updateMetricsConfig: (agentId: string, config: MetricsConfig) =>
    put<MetricsConfig>(`/agents/${agentId}/metrics-config`, config),

  loadDemo: () => post<LoadDemoResponse>("/demo", {}),

  listPlatforms: () => get<PlatformInfo[]>("/platforms"),

  getPlatformStatus: (platform: Platform) =>
    get<PlatformStatus>(`/platforms/${platform}/status`),

  configurePlatform: (platform: Platform, apiKey: string) =>
    post<PlatformStatus>(`/platforms/${platform}/configure`, { api_key: apiKey }),

  listRemoteAgents: (platform: Platform) =>
    get<RemoteAgentInfo[]>(`/platforms/${platform}/agents`),

  importRemoteAgent: (platform: Platform, agentId: string) =>
    post<AgentGraph>(`/platforms/${platform}/agents/${agentId}/import`, {}),

  exportToPlatform: (platform: Platform, graph: AgentGraph, name?: string) =>
    post<ExportToPlatformResponse>(`/platforms/${platform}/export`, { graph, name }),
};
