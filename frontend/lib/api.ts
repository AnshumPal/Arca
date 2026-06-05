// Typed API client for the Arca backend.
// All requests go through `request()` which handles base URL + JSON + errors.

import type {
  AgentOut,
  AgentVersion,
  ChatRequest,
  ChatResponse,
  EvalReport,
  EvalScore,
  HealthOut,
  OptimizerRunDetail,
  OptimizerRunSummary,
  Promotion,
  PromotionSummary,
  Rollback,
  SandboxCompare,
  SandboxDetail,
  SandboxOut,
  Trace,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(options.headers || {}),
    },
    cache: "no-store",
    ...options,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* keep default */
    }
    throw new ApiError(response.status, detail);
  }

  // 204 No Content
  if (response.status === 204) return undefined as T;
  return response.json();
}

// ─── Health & agents ──────────────────────────────────────────────────────────
export const getHealth = () => request<HealthOut>("/health");
export const getAgents = () => request<AgentOut[]>("/agents");

// ─── Chat & traces ────────────────────────────────────────────────────────────
export const postChat = (body: ChatRequest) =>
  request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const getTraces = (limit = 20, sessionId?: string) => {
  const params = new URLSearchParams({ limit: String(limit) });
  if (sessionId) params.set("session_id", sessionId);
  return request<Trace[]>(`/traces?${params.toString()}`);
};

export const postFeedback = (trace_id: string, feedback: 1 | -1) =>
  request<{ status: string }>("/feedback", {
    method: "POST",
    body: JSON.stringify({ trace_id, feedback }),
  });

// ─── Evaluation ───────────────────────────────────────────────────────────────
export const getEvalScores = (limit = 50) =>
  request<EvalScore[]>(`/eval/scores?limit=${limit}`);

export const getEvalReport = () => request<EvalReport>("/eval/report");

export const postEvalRun = (trace_id?: string) =>
  request<{ evaluated: number; skipped: number; message: string }>(
    "/eval/run",
    {
      method: "POST",
      body: JSON.stringify(trace_id ? { trace_id } : {}),
    }
  );

// ─── Sandbox ──────────────────────────────────────────────────────────────────
export const getSandboxes = (status?: string) => {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  const qs = params.toString();
  return request<SandboxOut[]>(`/sandbox${qs ? `?${qs}` : ""}`);
};

export const getSandboxDetail = (id: string) =>
  request<SandboxDetail>(`/sandbox/${id}`);

export const getSandboxCompare = (id: string) =>
  request<SandboxCompare>(`/sandbox/${id}/compare`);

export const deleteSandbox = (id: string, action: "suspend" | "delete" = "suspend") =>
  request<{ sandbox_id: string; status: string; message: string }>(
    `/sandbox/${id}?action=${action}`,
    { method: "DELETE" }
  );

// ─── Optimizer ────────────────────────────────────────────────────────────────
export const postOptimizerRun = () =>
  request<OptimizerRunSummary>("/optimizer/run", { method: "POST" });

export const getOptimizerRuns = (limit = 20) =>
  request<OptimizerRunSummary[]>(`/optimizer/runs?limit=${limit}`);

export const getOptimizerRunDetail = (id: string) =>
  request<OptimizerRunDetail>(`/optimizer/runs/${id}`);

// ─── Promotion ────────────────────────────────────────────────────────────────
export const postPromote = (sandbox_id: string) =>
  request<Promotion>(`/promote/${sandbox_id}`, { method: "POST" });

export const getPromotions = (status?: string) => {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  const qs = params.toString();
  return request<PromotionSummary[]>(`/promote${qs ? `?${qs}` : ""}`);
};

export const getPromotionDetail = (id: string) =>
  request<Promotion>(`/promote/${id}`);

export const approvePromotion = (id: string) =>
  request<{ promotion_id: string; status: string; agent_id: string; version_created: number; decided_at: string; message: string }>(
    `/promote/${id}/approve`,
    { method: "POST" }
  );

export const rejectPromotion = (id: string, reason: string) =>
  request<{ promotion_id: string; status: string; agent_id: string; rejection_reason: string; decided_at: string }>(
    `/promote/${id}/reject`,
    {
      method: "POST",
      body: JSON.stringify({ reason }),
    }
  );

// ─── Versions & rollbacks ─────────────────────────────────────────────────────
export const getAgentVersions = (agent_id: string) =>
  request<AgentVersion[]>(`/agents/${agent_id}/versions`);

export const rollbackAgent = (agent_id: string, to_version: number, reason?: string) =>
  request<Rollback>(`/agents/${agent_id}/rollback`, {
    method: "POST",
    body: JSON.stringify({ to_version, reason }),
  });

export const getRollbacks = (agent_id?: string) => {
  const params = new URLSearchParams();
  if (agent_id) params.set("agent_id", agent_id);
  const qs = params.toString();
  return request<Rollback[]>(`/rollbacks${qs ? `?${qs}` : ""}`);
};

export { ApiError };
