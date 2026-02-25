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
  state_prompt: string;
  tools?: ToolDefinition[];
  transitions: Transition[];
  metadata: Record<string, unknown>;
}

export interface AgentGraph {
  nodes: Record<string, AgentNode>;
  entry_node_id: string;
  source_type: string;
  source_metadata: Record<string, unknown>;
  snippets?: Record<string, string>;
  default_model?: string | null;
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
    agent: string | null;
    simulator: string | null;
    judge: string | null;
  };
  run: {
    max_turns: number;
    verbose: boolean;
    flow_judge: boolean;
    streaming: boolean;
    test_model_precedence: boolean;
    audio_eval: boolean;
  };
  audio: {
    tts_url: string;
    stt_url: string;
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
  tests_paths: string[] | null;
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
  source_path: string | null;
  source_index: number | null;
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
  test_case_id: string | null;
  call_id?: string | null;
  test_name: string;
  status: "pass" | "fail" | "error" | "running" | "cancelled";
  duration_ms: number | null;
  turn_count: number | null;
  end_reason: string | null;
  error_message: string | null;
  transcript_json: string | null;
  metrics_json: string | null;
  audio_metrics_json: string | null;
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

export interface PlatformInfo {
  name: string;
  configured: boolean;
  env_key: string;
  required_env_keys: string[];
}

export type Platform = string;

export interface RemoteAgentInfo {
  id: string;
  name: string;
}

export interface PlatformStatus {
  configured: boolean;
  platform: string;
}

export interface ExportToPlatformResponse {
  id: string;
  name: string;
  platform: string;
}

export interface RetryInfo {
  result_id: string;
  error_type: string;
  message: string;
  attempt: number;
  max_attempts: number;
  retry_after: number;
}

export interface SyncStatus {
  can_sync: boolean;
  reason: string | null;
  platform: string | null;
  remote_id: string | null;
  needs_configuration?: boolean;
}

export interface SyncToPlatformResponse {
  id: string;
  name: string;
  platform: string;
  synced: boolean;
}

export type CallStatus = "pending" | "connecting" | "active" | "ended" | "error";

export interface CallTranscriptMessage {
  role: "user" | "assistant";
  content: string;
}

export interface CallRecord {
  id: string;
  agent_id: string;
  room_name: string;
  status: CallStatus;
  transcript: CallTranscriptMessage[];
  started_at: string;
  ended_at: string | null;
}

export interface RunResult {
  run_id: string;
  message?: string;
  details?: Record<string, string>;
}

export interface StartCallResponse {
  call_id: string;
  room_name: string;
  livekit_url: string;
  token: string;
}

export interface StartChatResponse {
  chat_id: string;
}

export interface ExactMatch {
  text: string;
  locations: string[];
}

export interface FuzzyMatch {
  texts: string[];
  locations: string[];
  similarity: number;
}

export interface DryAnalysis {
  exact: ExactMatch[];
  fuzzy: FuzzyMatch[];
}

export interface FaultLocation {
  location_type: string;
  node_id?: string | null;
  transition_target_id?: string | null;
  relevant_text: string;
  explanation: string;
}

export interface Diagnosis {
  fault_locations: FaultLocation[];
  root_cause: string;
  transcript_evidence: string;
}

export interface PromptChange {
  location_type: string;
  node_id?: string | null;
  transition_target_id?: string | null;
  original_text: string;
  proposed_text: string;
  rationale: string;
}

export interface FixSuggestion {
  changes: PromptChange[];
  summary: string;
  confidence: number;
}

export interface DiagnoseResponse {
  diagnosis: Diagnosis;
  fix: FixSuggestion;
}

export interface ApplyFixResponse {
  iteration: number;
  changes_applied: PromptChange[];
  test_passed: boolean;
  metric_results: MetricResult[];
  improved: boolean;
  original_scores: Record<string, number>;
  new_scores: Record<string, number>;
}

export type AutoFixStopCondition = "improve" | "pass";
