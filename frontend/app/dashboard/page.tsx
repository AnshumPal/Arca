"use client";

import { useEffect, useState } from "react";
import { AgentBadge } from "@/components/AgentBadge";
import { ScoreBar } from "@/components/ScoreBar";
import { getEvalReport } from "@/lib/api";
import type { EvalReport } from "@/lib/types";

export default function DashboardPage() {
  const [report, setReport] = useState<EvalReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setReport(await getEvalReport());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); }, []);

  return (
    <div className="px-8 md:px-16 py-12">
      <header className="mb-12 flex items-end justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-[#8a8378] mb-2">
            Performance
          </p>
          <h1 className="display text-5xl">Dashboard</h1>
        </div>
        <button onClick={refresh} disabled={loading} className="btn-secondary">
          {loading ? "Loading…" : "Refresh"}
        </button>
      </header>

      {error && (
        <div className="card border-red-900/60 bg-red-950/40 text-red-200">
          {error}
        </div>
      )}

      {report && (
        <>
          <div className="mb-12 grid grid-cols-2 md:grid-cols-3 gap-8 pb-12 border-b border-[#1a1a1a]">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-[#5a5550] mb-2">
                Total evaluated
              </p>
              <p className="display text-4xl">{report.total_evaluated}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-[#5a5550] mb-2">
                Agents active
              </p>
              <p className="display text-4xl">{report.agents.length}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-[#5a5550] mb-2">
                Last generated
              </p>
              <p className="text-sm text-[#a8a09a] mt-3">
                {new Date(report.generated_at).toLocaleString()}
              </p>
            </div>
          </div>

          {report.agents.length === 0 ? (
            <div className="card text-center text-[#8a8378]">
              No evaluations yet. Send some chats to populate scores.
            </div>
          ) : (
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {report.agents.map((agent) => (
                <div key={agent.agent_id} className="card">
                  <div className="mb-6 flex items-center justify-between">
                    <AgentBadge agentId={agent.agent_id} />
                    <span className="text-xs text-[#5a5550] font-mono">
                      {agent.traces_evaluated} traces
                    </span>
                  </div>

                  <div className="mb-8">
                    <p className="text-xs uppercase tracking-wider text-[#5a5550] mb-2">
                      overall
                    </p>
                    <div className="flex items-baseline gap-2">
                      <span className="display text-6xl">
                        {agent.overall_avg.toFixed(2)}
                      </span>
                    </div>
                  </div>

                  <div className="space-y-4 pt-6 border-t border-[#1a1a1a]">
                    <ScoreBar label="latency"  value={agent.dimensions.latency} />
                    <ScoreBar label="length"   value={agent.dimensions.length} />
                    <ScoreBar label="feedback" value={agent.dimensions.feedback} />
                    <ScoreBar label="error"    value={agent.dimensions.error} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
