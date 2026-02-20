import type {
  AgentGraph,
  AgentRecord,
  CallRecord,
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
  RunResultRecord,
  RunWithResults,
  Settings,
  StartCallResponse,
  StartChatResponse,
  StartRunResponse,
  SyncStatus,
  SyncToPlatformResponse,
  TestCase,
  TestCaseRecord,
  TestResult,
  TestRun,
} from "./types";

export interface ApiClientConfig {
  baseUrl?: string;
  getHeaders?: () => Record<string, string> | Promise<Record<string, string>>;
}

let globalConfig: ApiClientConfig = {
  baseUrl: "/api",
};

export function configureApi(config: ApiClientConfig): void {
  globalConfig = { ...globalConfig, ...config };
}

export function getApiConfig(): ApiClientConfig {
  return globalConfig;
}

async function getHeaders(): Promise<Record<string, string>> {
  if (globalConfig.getHeaders) {
    return globalConfig.getHeaders();
  }
  return {};
}

import { etagCache } from "./etag-cache";

function parseErrorMessage(text: string, fallback: string): string {
  try {
    const json = JSON.parse(text);
    return json.detail || json.message || json.error || text;
  } catch {
    return text || fallback;
  }
}

async function get<T>(path: string): Promise<T> {
  const baseHeaders = await getHeaders();
  const headers = etagCache.buildHeaders(path, baseHeaders);

  const res = await fetch(`${globalConfig.baseUrl}${path}`, { headers });

  // Check for cached response on 304
  const cached = etagCache.handleResponse<T>(path, res);
  if (cached !== null) {
    return cached;
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(parseErrorMessage(text, res.statusText));
  }

  const text = await res.text();
  let data: T;
  try {
    data = JSON.parse(text);
  } catch (e) {
    throw new Error(`Invalid JSON from ${path}: ${text.slice(0, 100)}`);
  }

  // Cache if response has ETag
  etagCache.cacheResponse(path, res, data);

  return data;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const headers = await getHeaders();
  const res = await fetch(`${globalConfig.baseUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(parseErrorMessage(text, res.statusText));
  }
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch (e) {
    throw new Error(`Invalid JSON from POST ${path}: ${text.slice(0, 100)}`);
  }
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const headers = await getHeaders();
  const res = await fetch(`${globalConfig.baseUrl}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(parseErrorMessage(text, res.statusText));
  }
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch (e) {
    throw new Error(`Invalid JSON from PUT ${path}: ${text.slice(0, 100)}`);
  }
}

async function del<T>(path: string): Promise<T> {
  const headers = await getHeaders();
  const res = await fetch(`${globalConfig.baseUrl}${path}`, {
    method: "DELETE",
    headers,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(parseErrorMessage(text, res.statusText));
  }
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch (e) {
    throw new Error(`Invalid JSON from DELETE ${path}: ${text.slice(0, 100)}`);
  }
}

async function postFile<T>(path: string, file: File, source?: string): Promise<T> {
  const headers = await getHeaders();
  const formData = new FormData();
  formData.append("file", file);
  if (source) {
    formData.append("source", source);
  }
  const res = await fetch(`${globalConfig.baseUrl}${path}`, {
    method: "POST",
    headers,
    body: formData,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(parseErrorMessage(text, res.statusText));
  }
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch (e) {
    throw new Error(`Invalid JSON from POST ${path}: ${text.slice(0, 100)}`);
  }
}

export const api = {
  health: () => get<{ status: string }>("/health"),

  listImporters: () => get<ImporterInfo[]>("/importers"),

  listExporters: () => get<ExporterInfo[]>("/exporters"),

  importAgent: (config: unknown, source?: string) =>
    post<AgentGraph>("/agents/import", { config, source }),

  importAgentFile: (file: File, source?: string) =>
    postFile<AgentGraph>("/agents/import-file", file, source),

  createAgentFromFile: async (file: File, name?: string, source?: string) => {
    const headers = await getHeaders();
    const formData = new FormData();
    formData.append("file", file);
    if (name) formData.append("name", name);
    if (source) formData.append("source", source);
    const res = await fetch(`${globalConfig.baseUrl}/agents/upload`, {
      method: "POST",
      headers,
      body: formData,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || res.statusText);
    }
    return res.json() as Promise<AgentRecord>;
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

  updateAgent: (id: string, updates: { name?: string; default_model?: string; graph_json?: string }) =>
    put<AgentRecord>(`/agents/${id}`, updates),

  updatePrompt: (agentId: string, nodeId: string | null, promptText: string, transitionTargetId?: string) =>
    put<AgentGraph>(`/agents/${agentId}/prompts`, {
      node_id: nodeId,
      prompt_text: promptText,
      ...(transitionTargetId != null ? { transition_target_id: transitionTargetId } : {}),
    }),

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

  configurePlatform: (platform: Platform, apiKey: string, apiSecret?: string) =>
    post<PlatformStatus>(`/platforms/${platform}/configure`, { api_key: apiKey, api_secret: apiSecret }),

  listRemoteAgents: (platform: Platform) =>
    get<RemoteAgentInfo[]>(`/platforms/${platform}/agents`),

  importRemoteAgent: (platform: Platform, agentId: string) =>
    post<AgentGraph>(`/platforms/${platform}/agents/${agentId}/import`, {}),

  exportToPlatform: (platform: Platform, graph: AgentGraph, name?: string) =>
    post<ExportToPlatformResponse>(`/platforms/${platform}/export`, { graph, name }),

  getSyncStatus: (agentId: string) =>
    get<SyncStatus>(`/agents/${agentId}/sync-status`),

  syncToPlatform: (agentId: string, graph: AgentGraph) =>
    post<SyncToPlatformResponse>(`/agents/${agentId}/sync`, { graph }),

  getLiveKitStatus: () => get<{ available: boolean; error: string | null }>("/livekit/status"),

  startCall: (agentId: string) =>
    post<StartCallResponse>(`/agents/${agentId}/calls/start`, {}),

  getCall: (callId: string) => get<CallRecord>(`/calls/${callId}`),

  endCall: (callId: string) => post<{ status: string; call_id: string; run_id: string | null }>(`/calls/${callId}/end`, {}),

  startChat: (agentId: string) =>
    post<StartChatResponse>(`/agents/${agentId}/chats/start`, {}),

  endChat: (chatId: string) =>
    post<{ status: string; chat_id: string; run_id: string | null }>(`/chats/${chatId}/end`, {}),

  audioEvalResult: (resultId: string) =>
    post<RunResultRecord>(`/results/${resultId}/audio-eval`, {}),

  getWebSocketUrl: (path: string): string => {
    const baseUrl = globalConfig.baseUrl || "/api";
    if (baseUrl.startsWith("http://") || baseUrl.startsWith("https://")) {
      const url = new URL(baseUrl);
      const protocol = url.protocol === "https:" ? "wss:" : "ws:";
      return `${protocol}//${url.host}${url.pathname}${path}`;
    }
    if (typeof window !== "undefined") {
      // In development, connect directly to backend on port 8000
      // Vite proxy doesn't handle WebSocket upgrade reliably
      const host = window.location.hostname;
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      return `${protocol}//${host}:8000${baseUrl}${path}`;
    }
    return `ws://localhost:8000${baseUrl}${path}`;
  },
};
