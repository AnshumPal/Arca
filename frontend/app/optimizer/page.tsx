"use client";

import { useEffect, useState } from "react";
import { AgentBadge } from "@/components/AgentBadge";
import {
  getOptimizerRunDetail,
  getOptimizerRuns,
  postOptimizerRun,
} from "@/lib/api";
import type { OptimizerRunDetail, OptimizerRunSummary } from "@/lib/types";

const statusStyles: Record<string, string> = {
  completed: "border-[#6d7d5e]/40 bg-[#6d7d5e]/10 text-[#a8b89c]",
  failed:    "border-red-900/60 bg-red-950/40 text-red-300",
  running:   "border-[#c87f4a]/40 bg-[#c87f4a]/10 text-[#c87f4a]",
};

export default function OptimizerPage() {
  const [runs, setRuns] = useState<OptimizerRunSummary[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detail, setDetail] = useState<OptimizerRunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setRuns(await getOptimizerRuns(20));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); }, []);

  async function triggerRun() {
    if (!confirm("Trigger an optimizer cycle now? This may take 10–60s.")) return;
    setRunning(true);
    try {
      await postOptimizerRun();
      await refresh();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed");
    } finally {
      setRunning(false);
    }
  }

  async function expand(runId: string) {
    if (expanded === runId) { setExpanded(null); setDetail(null); return; }
    setExpanded(runId);
    setDetail(null);
    try {
      setDetail(await getOptimizerRunDetail(runId));
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed");
    }
  }

  return (
    <div className="px-8 md:px-16 py-12">
      <header className="mb-12 flex items-end justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-[#8a8378] mb-2">
            Autoresearch
          </p>
          <h1 className="display text-5xl">Optimizer</h1>
          <p className="mt-3 text-[#8a8378] max-w-xl">
            Nightly cycle finds failure patterns, calls the LLM for
            improvement proposals, and creates sandbox candidates.
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={refresh} disabled={loading} className="btn-secondary">
            {loading ? "…" : "Refresh"}
          </button>
          <button onClick={triggerRun} disabled={running} className="btn-copper">
            {running ? "Running…" : "Run now"}
          </button>
        </div>
      </header>

      {error && (
        <div className="card border-red-900/60 bg-red-950/40 text-red-200 mb-4">
          {error}
        </div>
      )}

      {runs.length === 0 ? (
        <div className="card text-center text-[#8a8378] py-16">
          No optimizer runs yet. Click <em>Run now</em>.
        </div>
      ) : (
        <div className="space-y-3">
          {runs.map((r) => (
            <div
              key={r.run_id}
              className="rounded-2xl border border-[#1a1a1a] bg-[#0d0d0d] overflow-hidden"
            >
              <button
                onClick={() => expand(r.run_id)}
                className="w-full px-6 py-5 flex items-center justify-between hover:bg-[#0a0a0a] transition-colors"
              >
                <div className="flex items-center gap-4 flex-1 min-w-0 text-left">
                  <span className={`badge border ${statusStyles[r.status] || "border-[#2a2a2a] text-[#8a8378]"}`}>
                    {r.status}
                  </span>
                  <span className="text-xs uppercase tracking-wider text-[#5a5550]">
                    {r.triggered_by}
                  </span>
                  <span className="font-mono text-xs text-[#5a5550]">
                    {r.run_id.slice(0, 8)}
                  </span>
                </div>
                <div className="hidden md:grid grid-cols-3 gap-12 mr-8 text-right">
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-[#5a5550]">Findings</p>
                    <p className="font-mono text-[#f5f1ea]">{r.findings_count}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-[#5a5550]">Proposals</p>
                    <p className="font-mono text-[#f5f1ea]">{r.proposals_count}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-[#5a5550]">Sandboxes</p>
                    <p className="font-mono text-[#c87f4a]">{r.sandboxes_created.length}</p>
                  </div>
                </div>
                <span className="text-xs text-[#5a5550] mr-3">
                  {new Date(r.started_at).toLocaleString()}
                </span>
                <span className="text-[#5a5550]">{expanded === r.run_id ? "−" : "+"}</span>
              </button>

              {expanded === r.run_id && (
                <div className="border-t border-[#1a1a1a] p-6 bg-[#050505]">
                  {!detail ? (
                    <p className="text-sm text-[#8a8378]">Loading detail…</p>
                  ) : (
                    <div className="space-y-6">
                      {detail.error && (
                        <div className="card border-red-900/60 bg-red-950/40 text-red-200 text-sm">
                          {detail.error}
                        </div>
                      )}

                      {detail.findings.length > 0 && (
                        <div>
                          <p className="text-xs uppercase tracking-[0.2em] text-[#5a5550] mb-3">
                            Findings · {detail.findings.length}
                          </p>
                          <div className="space-y-3">
                            {detail.findings.map((f, i) => (
                              <div key={i} className="rounded-xl border border-[#1a1a1a] p-4">
                                <div className="flex items-center gap-3 mb-2">
                                  <AgentBadge agentId={f.agent_id} />
                                  <span className="text-xs text-[#8a8378]">{f.dimension}</span>
                                  <span className="font-mono text-xs text-[#c87f4a]">
                                    {f.avg_score.toFixed(2)} / {f.threshold.toFixed(2)}
                                  </span>
                                </div>
                                <p className="text-sm text-[#a8a09a]">{f.diagnosis}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {detail.proposals.length > 0 && (
                        <div>
                          <p className="text-xs uppercase tracking-[0.2em] text-[#5a5550] mb-3">
                            Proposals · {detail.proposals.length}
                          </p>
                          <div className="space-y-3">
                            {detail.proposals.map((p, i) => (
                              <div key={i} className="rounded-xl border border-[#1a1a1a] p-4">
                                <div className="flex items-center gap-3 mb-3">
                                  <AgentBadge agentId={p.agent_id} />
                                  <span className="text-xs text-[#8a8378]">{p.dimension}</span>
                                </div>
                                <p className="text-sm text-[#a8a09a] mb-3">
                                  <span className="text-[#c87f4a]">Reasoning:</span> {p.reasoning}
                                </p>
                                <pre className="text-xs whitespace-pre-wrap break-words bg-[#0a0a0a] rounded p-3 text-[#a8a09a]">
                                  {p.proposed_prompt}
                                </pre>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
