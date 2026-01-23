export interface TransitionCondition {
  type: "llm_prompt" | "equation" | "tool_call" | "always";
  value: string;
}

export interface Transition {
  target_node_id: string;
  condition: TransitionCondition;
  description?: string;
}

export interface ToolDefinition {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  type?: string;
}

export interface AgentNode {
  id: string;
  instructions: string;
  tools?: ToolDefinition[];
  transitions: Transition[];
  metadata: Record<string, unknown>;
}

export interface AgentGraph {
  nodes: Record<string, AgentNode>;
  entry_node_id: string;
  source_type: string;
  source_metadata: Record<string, unknown>;
}

export interface Message {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  timestamp?: string;
  metadata: Record<string, unknown>;
}

export interface MetricResult {
  metric: string;
  passed: boolean;
  reasoning: string;
  score?: number;
  threshold?: number;
  confidence?: number;
}

export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
  result?: string;
}

export interface ModelsUsed {
  agent: string;
  simulator: string;
  judge: string;
}

export interface ModelOverride {
  role: string;
  requested: string;
  actual: string;
  reason: string;
}

export interface TestResult {
  test_id: string;
  test_name: string;
  status: "pass" | "fail" | "error" | "running" | "cancelled";
  transcript: Message[];
  metric_results: MetricResult[];
  nodes_visited: string[];
  tools_called: ToolCall[];
  constraint_violations: string[];
  turn_count: number;
  duration_ms: number;
  end_reason: string;
  error_message?: string;
  models_used?: ModelsUsed;
  model_overrides?: ModelOverride[];
}

export interface TestRun {
  run_id: string;
  started_at: string;
  completed_at?: string;
  results: TestResult[];
  passed_count: number;
  failed_count: number;
}

export type TestType = "llm" | "rule";

export interface TestCase {
  name: string;
  user_prompt: string;
  dynamic_variables: Record<string, unknown>;
  tool_mocks: unknown[];
  type: TestType | string;
  llm_model?: string;
  // LLM test fields
  metrics: string[];
  // Rule test fields
  includes: string[];
  excludes: string[];
  patterns: string[];
}

export interface RunOptions {
  max_turns: number;
  timeout_seconds: number;
  verbose: boolean;
  agent_model: string;
  simulator_model: string;
  judge_model: string;
}

export interface Settings {
  models: {
    agent: string;
    simulator: string;
    judge: string;
  };
  run: {
    max_turns: number;
    verbose: boolean;
    flow_judge: boolean;
  };
  env: Record<string, string>;
}

export interface ImporterInfo {
  source_type: string;
  description: string;
  file_patterns: string[];
}

export interface ExporterInfo {
  id: string;
  name: string;
  description: string;
  ext: string;
}

export interface GlobalMetric {
  name: string;
  criteria: string;
  threshold?: number | null;
  enabled: boolean;
}

export interface MetricsConfig {
  threshold: number;
  global_metrics: GlobalMetric[];
}

export interface AgentRecord {
  id: string;
  name: string;
  source_type: string;
  source_path: string | null;
  graph_json: string | null;
  metrics_config?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TestCaseRecord {
  id: string;
  agent_id: string;
  name: string;
  user_prompt: string;
  metrics: string;
  dynamic_variables: string;
  tool_mocks: string;
  type: string;
  llm_model: string | null;
  includes: string | null;
  excludes: string | null;
  patterns: string | null;
  created_at: string;
  updated_at: string;
}

export interface GalleryItem {
  id: string;
  name: string;
  description: string;
  tests: TestCase[];
}

export interface RunRecord {
  id: string;
  agent_id: string;
  started_at: string;
  completed_at: string | null;
}

export interface RunResultRecord {
  id: string;
  run_id: string;
  test_case_id: string;
  test_name: string;
  status: "pass" | "fail" | "error" | "running" | "cancelled";
  duration_ms: number | null;
  turn_count: number | null;
  end_reason: string | null;
  error_message: string | null;
  transcript_json: string | null;
  metrics_json: string | null;
  nodes_visited: string | null;
  tools_called: string | null;
  models_used: string | null;
  created_at: string;
}

export interface RunWithResults extends RunRecord {
  results: RunResultRecord[];
}

export interface StartRunResponse {
  id: string;
  agent_id: string;
  started_at: string;
  test_count: number;
}

export interface LoadDemoResponse {
  agent_id: string;
  agent_name: string;
  test_count: number;
  created: boolean;
}
