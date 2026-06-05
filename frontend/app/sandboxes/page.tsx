"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AgentBadge } from "@/components/AgentBadge";
import { getSandboxes } from "@/lib/api";
import type { SandboxOut } from "@/lib/types";

const statusStyles: Record<string, string> = {
  active:    "border-[#6d7d5e]/40 bg-[#6d7d5e]/10 text-[#a8b89c]",
  suspended: "border-[#c87f4a]/40 bg-[#c87f4a]/10 text-[#c87f4a]",
  deleted:   "border-[#2a2a2a] bg-[#0d0d0d] text-[#5a5550]",
};

export default function SandboxesPage() {
  const [sandboxes, setSandboxes] = useState<SandboxOut[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setSandboxes(await getSandboxes(statusFilter || undefined));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [statusFilter]);

  return (
    <div className="px-8 md:px-16 py-12">
      <header className="mb-12 flex items-end justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-[#8a8378] mb-2">
            Shadow agents
          </p>
          <h1 className="display text-5xl">Sandboxes</h1>
          <p className="mt-3 text-[#8a8378] max-w-xl">
            Experimental copies running silently against live traffic. They
            never respond to users — only learn.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-full border border-[#2a2a2a] bg-transparent px-4 py-2 text-sm"
          >
            <option value="">All</option>
            <option value="active">Active</option>
            <option value="suspended">Suspended</option>
            <option value="deleted">Deleted</option>
          </select>
          <button onClick={refresh} disabled={loading} className="btn-secondary">
            {loading ? "…" : "Refresh"}
          </button>
        </div>
      </header>

      {error && (
        <div className="card border-red-900/60 bg-red-950/40 text-red-200 mb-4">
          {error}
        </div>
      )}

      {sandboxes.length === 0 ? (
        <div className="card text-center text-[#8a8378] py-16">
          No sandboxes yet. Run the optimizer or create one directly.
        </div>
      ) : (
        <div className="grid gap-3">
          {sandboxes.map((s) => (
            <Link
              key={s.sandbox_id}
              href={`/sandboxes/${s.sandbox_id}`}
              className="group rounded-2xl border border-[#1a1a1a] bg-[#0d0d0d] px-6 py-5 flex items-center justify-between hover:border-[#c87f4a]/40 transition-colors"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3 mb-2">
                  <AgentBadge agentId={s.production_agent_id} />
                  <span className={`badge border ${statusStyles[s.status]}`}>
                    {s.status}
                  </span>
                </div>
                <h3 className="display text-xl truncate group-hover:text-[#c87f4a] transition-colors">
                  {s.name}
                </h3>
              </div>

              <div className="hidden md:grid grid-cols-3 gap-12 mr-8 text-right">
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-[#5a5550] mb-1">
                    Traces
                  </p>
                  <p className="font-mono text-[#f5f1ea]">{s.trace_count}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-[#5a5550] mb-1">
                    Avg score
                  </p>
                  <p className="font-mono text-[#f5f1ea]">
                    {s.avg_overall_score !== null ? s.avg_overall_score.toFixed(3) : "—"}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-[#5a5550] mb-1">
                    Created
                  </p>
                  <p className="text-xs text-[#a8a09a]">
                    {new Date(s.created_at).toLocaleDateString()}
                  </p>
                </div>
              </div>

              <span className="text-[#5a5550] group-hover:text-[#c87f4a] transition-colors">
                →
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
