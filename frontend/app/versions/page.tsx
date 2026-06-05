"use client";

import { useEffect, useState } from "react";
import { AgentBadge } from "@/components/AgentBadge";
import { getAgentVersions, getRollbacks, rollbackAgent } from "@/lib/api";
import type { AgentVersion, Rollback } from "@/lib/types";

const agents = ["agent-1", "agent-2", "agent-3"];

export default function VersionsPage() {
  const [selectedAgent, setSelectedAgent] = useState("agent-1");
  const [versions, setVersions] = useState<AgentVersion[]>([]);
  const [rollbacks, setRollbacks] = useState<Rollback[]>([]);
  const [, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [vs, rs] = await Promise.all([
        getAgentVersions(selectedAgent),
        getRollbacks(selectedAgent),
      ]);
      setVersions(vs);
      setRollbacks(rs);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [selectedAgent]);

  async function handleRollback(to_version: number) {
    const reason = prompt(`Roll back ${selectedAgent} to v${to_version}. Reason?`);
    if (!reason) return;
    setWorking(true);
    try {
      await rollbackAgent(selectedAgent, to_version, reason);
      await refresh();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed");
    } finally {
      setWorking(false);
    }
  }

  return (
    <div className="px-8 md:px-16 py-12">
      <header className="mb-12 flex items-end justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-[#8a8378] mb-2">
            History
          </p>
          <h1 className="display text-5xl">Versions</h1>
          <p className="mt-3 text-[#8a8378] max-w-xl">
            Every prompt change ever shipped. Rollback to any previous version
            in 30 seconds.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {agents.map((a) => (
            <button
              key={a}
              onClick={() => setSelectedAgent(a)}
              className={`btn ${
                selectedAgent === a
                  ? "bg-[#c87f4a] text-white"
                  : "border border-[#2a2a2a] text-[#a8a09a] hover:border-[#4a4a4a]"
              }`}
            >
              <AgentBadge agentId={a} />
            </button>
          ))}
        </div>
      </header>

      {error && (
        <div className="card border-red-900/60 bg-red-950/40 text-red-200 mb-4">
          {error}
        </div>
      )}

      {versions.length === 0 ? (
        <div className="card text-center text-[#8a8378] py-16">
          No versions recorded for {selectedAgent} yet. Approve a promotion to
          create version 1.
        </div>
      ) : (
        <div className="relative space-y-6">
          {/* Vertical timeline line */}
          <div className="absolute left-3 top-0 bottom-0 w-px bg-[#1a1a1a]" />

          {versions.map((v) => (
            <div key={v.version} className="relative pl-12">
              <div
                className={`absolute left-0 top-3 h-6 w-6 rounded-full border-2 ${
                  v.is_current
                    ? "border-[#c87f4a] bg-[#c87f4a]"
                    : "border-[#2a2a2a] bg-[#0d0d0d]"
                }`}
              />

              <div className="card">
                <div className="mb-4 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="display text-3xl">v{v.version}</span>
                    {v.is_current && (
                      <span className="badge border border-[#c87f4a]/40 bg-[#c87f4a]/10 text-[#c87f4a]">
                        Live
                      </span>
                    )}
                    <span className="text-xs text-[#5a5550]">
                      {new Date(v.created_at).toLocaleString()}
                    </span>
                  </div>
                  {!v.is_current && (
                    <button
                      onClick={() => handleRollback(v.version)}
                      disabled={working}
                      className="btn-secondary text-xs"
                    >
                      Roll back here
                    </button>
                  )}
                </div>

                {v.promoted_from && (
                  <p className="text-xs text-[#5a5550] mb-3 font-mono">
                    promoted_from: {v.promoted_from.slice(0, 8)}
                  </p>
                )}

                <pre className="whitespace-pre-wrap break-words rounded-lg bg-[#050505] p-4 text-xs text-[#a8a09a] leading-relaxed">
                  {v.system_prompt}
                </pre>
              </div>
            </div>
          ))}
        </div>
      )}

      {rollbacks.length > 0 && (
        <div className="mt-16">
          <p className="text-xs uppercase tracking-[0.2em] text-[#5a5550] mb-4">
            Rollback log
          </p>
          <div className="space-y-2">
            {rollbacks.map((rb) => (
              <div
                key={rb.rollback_id}
                className="rounded-xl border border-[#1a1a1a] bg-[#0d0d0d] px-5 py-3 flex items-center justify-between"
              >
                <div className="text-sm">
                  <span className="text-[#a8a09a]">
                    v{rb.from_version} → v{rb.to_version}
                  </span>
                  {rb.reason && (
                    <span className="text-[#8a8378] ml-3">· {rb.reason}</span>
                  )}
                </div>
                <span className="text-xs text-[#5a5550]">
                  {new Date(rb.rolled_back_at).toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
