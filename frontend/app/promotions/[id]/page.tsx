"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AgentBadge } from "@/components/AgentBadge";
import {
  approvePromotion,
  getPromotionDetail,
  rejectPromotion,
} from "@/lib/api";
import type { Promotion } from "@/lib/types";

export default function PromotionDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const [promo, setPromo] = useState<Promotion | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setPromo(await getPromotionDetail(params.id));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [params.id]);

  async function handleApprove() {
    if (!confirm("Approve and promote? Agent will go live within 30s.")) return;
    setWorking(true);
    try {
      await approvePromotion(params.id);
      await refresh();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed");
    } finally {
      setWorking(false);
    }
  }

  async function handleReject() {
    const reason = prompt("Reason for rejection?");
    if (!reason) return;
    setWorking(true);
    try {
      await rejectPromotion(params.id, reason);
      await refresh();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed");
    } finally {
      setWorking(false);
    }
  }

  if (loading && !promo) return <div className="px-8 md:px-16 py-12 text-[#8a8378]">Loading…</div>;
  if (error) return <div className="px-8 md:px-16 py-12"><div className="card border-red-900/60 bg-red-950/40 text-red-200">{error}</div></div>;
  if (!promo) return null;

  return (
    <div className="px-8 md:px-16 py-12">
      <Link href="/promotions" className="text-xs uppercase tracking-[0.2em] text-[#8a8378] hover:text-[#f5f1ea]">
        ← Promotions
      </Link>

      <header className="mt-4 mb-12">
        <div className="flex items-center gap-3 mb-4">
          <AgentBadge agentId={promo.agent_id} />
          <span className={`badge border ${
            promo.status === "pending"  ? "border-[#c87f4a]/40 bg-[#c87f4a]/10 text-[#c87f4a]"
              : promo.status === "approved" ? "border-[#6d7d5e]/40 bg-[#6d7d5e]/10 text-[#a8b89c]"
              : "border-red-900/60 bg-red-950/40 text-red-300"
          }`}>
            {promo.status}
          </span>
        </div>
        <h1 className="display text-4xl mb-3">Promotion request</h1>
        <p className="text-xs font-mono text-[#5a5550]">{promo.promotion_id}</p>

        {promo.status === "pending" && (
          <div className="mt-6 flex gap-2">
            <button onClick={handleApprove} disabled={working} className="btn-copper">
              Approve →
            </button>
            <button onClick={handleReject} disabled={working} className="btn-danger">
              Reject
            </button>
          </div>
        )}

        {promo.status === "approved" && promo.version_created && (
          <div className="mt-6 text-sm text-[#a8b89c]">
            Promoted to version {promo.version_created} at{" "}
            {promo.decided_at && new Date(promo.decided_at).toLocaleString()}
          </div>
        )}

        {promo.status === "rejected" && (
          <div className="mt-6 rounded-xl border border-red-900/60 bg-red-950/30 p-4 text-sm">
            <p className="text-red-300">Reason: {promo.rejection_reason}</p>
          </div>
        )}
      </header>

      <div className="card">
        <div className="mb-6 flex items-center justify-between">
          <p className="text-xs uppercase tracking-[0.2em] text-[#5a5550]">
            Gate checks
          </p>
          <span className={`badge border ${
            promo.gate_results.passed
              ? "border-[#6d7d5e]/40 bg-[#6d7d5e]/10 text-[#a8b89c]"
              : "border-red-900/60 bg-red-950/40 text-red-300"
          }`}>
            {promo.gate_results.summary}
          </span>
        </div>

        <div className="space-y-2">
          {promo.gate_results.checks.map((c, i) => (
            <div
              key={i}
              className={`rounded-xl border px-4 py-3 ${
                c.passed
                  ? "border-[#1a1a1a] bg-[#0a0a0a]"
                  : "border-red-900/40 bg-red-950/20"
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-3">
                  <span className={c.passed ? "text-[#a8b89c]" : "text-red-300"}>
                    {c.passed ? "✓" : "✗"}
                  </span>
                  <span className="text-sm capitalize">{c.name.replace(/_/g, " ")}</span>
                </div>
                <span className="font-mono text-xs text-[#8a8378]">
                  {c.value} / {c.threshold}
                </span>
              </div>
              <p className="text-xs text-[#8a8378] pl-7">{c.message}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
