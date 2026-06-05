"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AgentBadge } from "@/components/AgentBadge";
import { getPromotions } from "@/lib/api";
import type { PromotionSummary } from "@/lib/types";

const statusStyles: Record<string, string> = {
  pending:  "border-[#c87f4a]/40 bg-[#c87f4a]/10 text-[#c87f4a]",
  approved: "border-[#6d7d5e]/40 bg-[#6d7d5e]/10 text-[#a8b89c]",
  rejected: "border-red-900/60 bg-red-950/40 text-red-300",
};

export default function PromotionsPage() {
  const [items, setItems] = useState<PromotionSummary[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setItems(await getPromotions(statusFilter || undefined));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed");
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
            Approval queue
          </p>
          <h1 className="display text-5xl">Promotions</h1>
          <p className="mt-3 text-[#8a8378] max-w-xl">
            The gate advises, you decide. Nothing reaches production without an
            explicit approve.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-full border border-[#2a2a2a] bg-transparent px-4 py-2 text-sm"
          >
            <option value="">All</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
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

      {items.length === 0 ? (
        <div className="card text-center text-[#8a8378] py-16">
          No promotion requests yet.
        </div>
      ) : (
        <div className="grid gap-3">
          {items.map((p) => (
            <Link
              key={p.promotion_id}
              href={`/promotions/${p.promotion_id}`}
              className="group rounded-2xl border border-[#1a1a1a] bg-[#0d0d0d] px-6 py-5 flex items-center justify-between hover:border-[#c87f4a]/40 transition-colors"
            >
              <div className="flex-1 min-w-0 flex items-center gap-4">
                <span className={`badge border ${statusStyles[p.status]}`}>
                  {p.status}
                </span>
                <AgentBadge agentId={p.agent_id} />
                <span className="text-sm text-[#8a8378]">
                  gate{" "}
                  <span className={p.gate_passed ? "text-[#a8b89c]" : "text-red-300"}>
                    {p.gate_passed === null ? "—" : p.gate_passed ? "✓ pass" : "✗ fail"}
                  </span>
                </span>
                {p.version_created && (
                  <span className="text-sm text-[#c87f4a] font-mono">
                    → v{p.version_created}
                  </span>
                )}
              </div>
              <div className="text-xs text-[#5a5550] mr-3">
                {new Date(p.requested_at).toLocaleString()}
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
