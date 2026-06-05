"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AgentBadge } from "@/components/AgentBadge";
import { ScoreBar } from "@/components/ScoreBar";
import {
  deleteSandbox,
  getSandboxCompare,
  getSandboxDetail,
  postPromote,
} from "@/lib/api";
import type { SandboxCompare, SandboxDetail } from "@/lib/types";
import { useRouter } from "next/navigation";

export default function SandboxDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const router = useRouter();
  const [detail, setDetail] = useState<SandboxDetail | null>(null);
  const [compare, setCompare] = useState<SandboxCompare | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [d, c] = await Promise.all([
        getSandboxDetail(params.id),
        getSandboxCompare(params.id),
      ]);
      setDetail(d);
      setCompare(c);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [params.id]);

  async function handlePromote() {
    if (!confirm("Request promotion? Gate will run automatically.")) return;
    setWorking(true);
    try {
      const promo = await postPromote(params.id);
      router.push(`/promotions/${promo.promotion_id}`);
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed");
    } finally {
      setWorking(false);
    }
  }

  async function handleSuspend(action: "suspend" | "delete") {
    if (!confirm(`Confirm ${action}?`)) return;
    setWorking(true);
    try {
      await deleteSandbox(params.id, action);
      await refresh();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed");
    } finally {
      setWorking(false);
    }
  }

  if (loading && !detail) return <div className="px-8 md:px-16 py-12 text-[#8a8378]">Loading…</div>;
  if (error) return <div className="px-8 md:px-16 py-12"><div className="card border-red-900/60 bg-red-950/40 text-red-200">{error}</div></div>;
  if (!detail) return null;

  const cfg = detail.config as Record<string, unknown>;

  return (
    <div className="px-8 md:px-16 py-12">
      <Link href="/sandboxes" className="text-xs uppercase tracking-[0.2em] text-[#8a8378] hover:text-[#f5f1ea]">
        ← Sandboxes
      </Link>

      <header className="mt-4 mb-12">
        <div className="flex items-center gap-3 mb-4">
          <AgentBadge agentId={detail.production_agent_id} />
          <span className="badge border border-[#2a2a2a] text-[#a8a09a]">
            {detail.status}
          </span>
        </div>
        <h1 className="display text-5xl mb-3">{detail.name}</h1>
        <p className="text-xs font-mono text-[#5a5550]">{detail.sandbox_id}</p>

        {detail.status === "active" && (
          <div className="mt-6 flex gap-2">
            <button
              onClick={handlePromote}
              disabled={working || detail.trace_count < 10}
              className="btn-copper"
              title={detail.trace_count < 10 ? "Need 10+ traces" : "Request promotion"}
            >
              Request promotion →
            </button>
            <button
              onClick={() => handleSuspend("suspend")}
              disabled={working}
              className="btn-secondary"
            >
              Suspend
            </button>
            <button
              onClick={() => handleSuspend("delete")}
              disabled={working}
              className="btn-danger"
            >
              Delete
            </button>
          </div>
        )}
      </header>

      <div className="grid gap-6 lg:grid-cols-2 mb-6">
        <div className="card">
          <p className="text-xs uppercase tracking-[0.2em] text-[#5a5550] mb-4">
            Config diff from production
          </p>
          <div className="space-y-3 text-sm">
            <div>
              <span className="text-[#8a8378]">model</span>
              <span className="float-right font-mono">{String(cfg.model ?? "—")}</span>
            </div>
            <div>
              <span className="text-[#8a8378]">temperature</span>
              <span className="float-right font-mono">{String(cfg.temperature ?? "—")}</span>
            </div>
            {cfg.system_prompt ? (
              <div className="pt-3 border-t border-[#1a1a1a]">
                <p className="text-[#8a8378] mb-2">system_prompt</p>
                <pre className="whitespace-pre-wrap break-words rounded-lg bg-[#050505] p-4 text-xs text-[#a8a09a] leading-relaxed">
                  {String(cfg.system_prompt)}
                </pre>
              </div>
            ) : null}
          </div>
        </div>

        <div className="card">
          <p className="text-xs uppercase tracking-[0.2em] text-[#5a5550] mb-4">
            Sandbox averages · {detail.trace_count} traces
          </p>
          {detail.dimension_averages && detail.avg_overall_score !== null ? (
            <>
              <div className="mb-6 pb-6 border-b border-[#1a1a1a]">
                <p className="text-xs text-[#8a8378] mb-1">overall</p>
                <p className="display text-5xl">
                  {detail.avg_overall_score.toFixed(2)}
                </p>
              </div>
              <div className="space-y-4">
                <ScoreBar label="latency"  value={detail.dimension_averages.latency} />
                <ScoreBar label="length"   value={detail.dimension_averages.length} />
                <ScoreBar label="feedback" value={detail.dimension_averages.feedback} />
                <ScoreBar label="error"    value={detail.dimension_averages.error} />
              </div>
            </>
          ) : (
            <p className="text-[#8a8378] text-sm">No scores yet.</p>
          )}
        </div>
      </div>

      {compare && (
        <div className="card">
          <div className="mb-6 flex items-center justify-between">
            <p className="text-xs uppercase tracking-[0.2em] text-[#5a5550]">
              Sandbox vs production baseline
            </p>
            <span
              className={`badge border ${
                compare.verdict === "sandbox_better"
                  ? "border-[#6d7d5e]/40 bg-[#6d7d5e]/10 text-[#a8b89c]"
                  : compare.verdict === "production_better"
                  ? "border-red-900/60 bg-red-950/40 text-red-300"
                  : compare.verdict === "tied"
                  ? "border-[#c87f4a]/40 bg-[#c87f4a]/10 text-[#c87f4a]"
                  : "border-[#2a2a2a] text-[#8a8378]"
              }`}
            >
              {compare.verdict.replace("_", " ")}
            </span>
          </div>

          {compare.verdict === "insufficient_data" ? (
            <p className="text-sm text-[#8a8378]">
              {compare.sandbox_trace_count} of {compare.min_traces_required} traces collected.
              Need {compare.min_traces_required - compare.sandbox_trace_count} more before a verdict can be issued.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs uppercase tracking-wider text-[#5a5550]">
                  <th className="py-3 text-left font-normal">Dimension</th>
                  <th className="py-3 text-right font-normal">Production</th>
                  <th className="py-3 text-right font-normal">Sandbox</th>
                  <th className="py-3 text-right font-normal">Δ</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1a1a1a]">
                {Object.entries(compare.comparison).map(([dim, vals]) => (
                  <tr key={dim}>
                    <td className="py-3 capitalize text-[#a8a09a]">{dim}</td>
                    <td className="py-3 text-right font-mono">{vals.production.toFixed(3)}</td>
                    <td className="py-3 text-right font-mono">{vals.sandbox.toFixed(3)}</td>
                    <td
                      className={`py-3 text-right font-mono ${
                        vals.delta > 0 ? "text-[#a8b89c]" : vals.delta < 0 ? "text-red-300" : "text-[#5a5550]"
                      }`}
                    >
                      {vals.delta > 0 ? "+" : ""}{vals.delta.toFixed(3)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
