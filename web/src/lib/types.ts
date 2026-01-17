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
  status: "pass" | "fail" | "error";
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

export interface TestCase {
  name: string;
  user_prompt: string;
  metrics: string[];
  dynamic_variables: Record<string, unknown>;
  tool_mocks: unknown[];
  type: string;
  llm_model?: string;
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
  };
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
}
