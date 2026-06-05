// Shared TypeScript types — mirrors the Pydantic schemas in the backend

export interface ChatRequest {
  message: string;
  session_id?: string;
}

export interface ChatResponse {
  response: string;
  trace_id: string;
  agent_id: string;
  latency_ms: number;
}

export interface Trace {
  id: string;
  session_id: string | null;
  agent_id: string;
  input: string;
  output: string | null;
  latency_ms: number | null;
  feedback: number | null;
  created_at: string;
}

export interface AgentOut {
  agent_id: string;
  description: string;
}

export interface HealthOut {
  status: string;
  env: string;
  agents_active: number;
}

export interface DimensionScore {
  dimension: string;
  score: number;
  reasoning: string;
}

export interface EvalScore {
  trace_id: string;
  agent_id: string;
  overall_score: number;
  evaluated_at: string;
  dimensions: DimensionScore[];
}

export interface AgentDimensionAvg {
  latency: number;
  length: number;
  feedback: number;
  error: number;
}

export interface AgentReportEntry {
  agent_id: string;
  traces_evaluated: number;
  overall_avg: number;
  dimensions: AgentDimensionAvg;
}

export interface EvalReport {
  generated_at: string;
  total_evaluated: number;
  agents: AgentReportEntry[];
}

export interface SandboxOut {
  sandbox_id: string;
  name: string;
  production_agent_id: string;
  status: string;
  config: Record<string, unknown>;
  trace_count: number;
  avg_overall_score: number | null;
  created_at: string;
}

export interface SandboxDetail extends SandboxOut {
  dimension_averages: AgentDimensionAvg | null;
}

export interface ComparisonDimension {
  production: number;
  sandbox: number;
  delta: number;
}

export interface SandboxCompare {
  sandbox_id: string;
  sandbox_name: string;
  production_agent_id: string;
  verdict: string;
  min_traces_required: number;
  sandbox_trace_count: number;
  comparison: Record<string, ComparisonDimension>;
}

export interface OptimizerRunSummary {
  run_id: string;
  status: string;
  triggered_by: string;
  findings_count: number;
  proposals_count: number;
  sandboxes_created: string[];
  error: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface FailurePattern {
  agent_id: string;
  dimension: string;
  avg_score: number;
  threshold: number;
  sample_count: number;
  sample_inputs: string[];
  diagnosis: string;
}

export interface Proposal {
  agent_id: string;
  dimension: string;
  original_prompt: string;
  proposed_prompt: string;
  reasoning: string;
  sandbox_config: Record<string, unknown>;
}

export interface OptimizerRunDetail extends OptimizerRunSummary {
  agents_analyzed: string[];
  findings: FailurePattern[];
  proposals: Proposal[];
}

export interface GateCheck {
  name: string;
  passed: boolean;
  value: number | string;
  threshold: number | string;
  message: string;
}

export interface GateResult {
  passed: boolean;
  summary: string;
  checks: GateCheck[];
}

export interface PromotionSummary {
  promotion_id: string;
  sandbox_id: string;
  agent_id: string;
  status: string;
  gate_passed: boolean | null;
  requested_at: string;
  decided_at: string | null;
  version_created: number | null;
}

export interface Promotion extends PromotionSummary {
  gate_results: GateResult;
  decided_by: string | null;
  rejection_reason: string | null;
}

export interface AgentVersion {
  version: number;
  is_current: boolean;
  system_prompt: string;
  promoted_from: string | null;
  created_at: string;
}

export interface Rollback {
  rollback_id: string;
  agent_id: string;
  from_version: number;
  to_version: number;
  reason: string | null;
  rolled_back_at: string;
  message: string;
}
