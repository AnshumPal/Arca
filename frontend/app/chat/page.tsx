"use client";

import { useEffect, useRef, useState } from "react";
import { AgentBadge } from "@/components/AgentBadge";
import { postChat, postFeedback } from "@/lib/api";
import type { ChatResponse } from "@/lib/types";

interface Turn {
  role: "user" | "assistant";
  content: string;
  trace_id?: string;
  agent_id?: string;
  latency_ms?: number;
  feedback?: 1 | -1 | null;
}

export default function ChatPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId] = useState(() => `web-${Date.now()}`);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  async function send() {
    const message = input.trim();
    if (!message || loading) return;
    setError(null);
    setTurns((t) => [...t, { role: "user", content: message }]);
    setInput("");
    setLoading(true);
    try {
      const res: ChatResponse = await postChat({ message, session_id: sessionId });
      setTurns((t) => [
        ...t,
        {
          role: "assistant",
          content: res.response,
          trace_id: res.trace_id,
          agent_id: res.agent_id,
          latency_ms: res.latency_ms,
          feedback: null,
        },
      ]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
      setTurns((t) => t.slice(0, -1));
    } finally {
      setLoading(false);
    }
  }

  async function rate(idx: number, value: 1 | -1) {
    const t = turns[idx];
    if (!t.trace_id) return;
    try {
      await postFeedback(t.trace_id, value);
      setTurns((arr) =>
        arr.map((tu, i) => (i === idx ? { ...tu, feedback: value } : tu))
      );
    } catch (e) {
      console.error(e);
    }
  }

  const prompts = [
    { text: "hello, how are you", agent: "intake" },
    { text: "explain how transformers work", agent: "research" },
    { text: "write a poem about the ocean", agent: "action" },
  ];

  return (
    <div className="flex h-screen flex-col px-8 md:px-16 py-12">
      <header className="mb-8 flex items-end justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-[#8a8378] mb-2">
            Live conversation
          </p>
          <h1 className="display text-5xl">Chat</h1>
        </div>
        <span className="text-xs font-mono text-[#5a5550]">
          session · {sessionId.slice(-8)}
        </span>
      </header>

      <div className="flex-1 overflow-y-auto pr-4 -mr-4 space-y-8 mb-6">
        {turns.length === 0 && (
          <div className="grid h-full place-items-center text-center">
            <div className="max-w-md">
              <p className="text-sm uppercase tracking-[0.2em] text-[#5a5550] mb-6">
                Try one of these
              </p>
              <div className="flex flex-col gap-3">
                {prompts.map((p) => (
                  <button
                    key={p.text}
                    onClick={() => setInput(p.text)}
                    className="group flex items-center justify-between rounded-xl border border-[#1a1a1a] px-5 py-4 text-left hover:border-[#c87f4a]/40 transition-colors"
                  >
                    <span className="text-[#f5f1ea]">&ldquo;{p.text}&rdquo;</span>
                    <span className="text-xs uppercase tracking-wider text-[#5a5550] group-hover:text-[#c87f4a]">
                      {p.agent} →
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {turns.map((t, i) => (
          <div key={i}>
            {t.role === "user" ? (
              <div className="text-right">
                <p className="display text-xl md:text-2xl text-[#f5f1ea] inline-block max-w-2xl">
                  &ldquo;{t.content}&rdquo;
                </p>
              </div>
            ) : (
              <div>
                {t.agent_id && (
                  <div className="flex items-center gap-3 mb-3 text-xs">
                    <AgentBadge agentId={t.agent_id} />
                    <span className="text-[#5a5550]">·</span>
                    <span className="font-mono text-[#8a8378]">
                      {t.latency_ms}ms
                    </span>
                    <span className="text-[#5a5550]">·</span>
                    <span className="font-mono text-[#5a5550]">
                      {t.trace_id?.slice(0, 8)}
                    </span>
                  </div>
                )}
                <p className="whitespace-pre-wrap text-[#a8a09a] leading-relaxed max-w-3xl">
                  {t.content}
                </p>
                {t.trace_id && (
                  <div className="mt-6 max-w-3xl">
                    {t.feedback === null ? (
                      <div className="flex items-center justify-between rounded-2xl border border-[#c87f4a]/30 bg-[#c87f4a]/5 px-5 py-4">
                        <span className="text-sm text-[#f5f1ea]">
                          Was this helpful?{" "}
                          <span className="text-[#8a8378]">
                            (your feedback trains the optimizer)
                          </span>
                        </span>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => rate(i, 1)}
                            className="btn-copper text-sm px-4 py-2"
                            aria-label="Mark helpful"
                          >
                            👍 Yes
                          </button>
                          <button
                            onClick={() => rate(i, -1)}
                            className="btn-secondary text-sm px-4 py-2"
                            aria-label="Mark not helpful"
                          >
                            👎 No
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div
                        className={`flex items-center gap-3 rounded-2xl border px-5 py-3 text-sm ${
                          t.feedback === 1
                            ? "border-[#c87f4a]/40 bg-[#c87f4a]/10 text-[#c87f4a]"
                            : "border-red-900/40 bg-red-950/30 text-red-300"
                        }`}
                      >
                        <span>
                          {t.feedback === 1 ? "👍" : "👎"}
                        </span>
                        <span>
                          {t.feedback === 1
                            ? "Thanks — feedback recorded."
                            : "Noted — this feeds into the next optimizer cycle."}
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="text-sm text-[#5a5550] animate-pulse">
            Thinking…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {error && (
        <div className="mb-4 rounded-xl border border-red-900/60 bg-red-950/40 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}

      <div className="flex gap-3 items-end border-t border-[#1a1a1a] pt-6">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask anything…"
          disabled={loading}
          className="flex-1 bg-transparent border-0 border-b border-[#2a2a2a] focus:border-[#c87f4a] outline-none py-3 text-lg placeholder-[#5a5550] disabled:opacity-50 transition-colors"
        />
        <button
          onClick={send}
          disabled={loading || !input.trim()}
          className="btn-primary"
        >
          Send →
        </button>
      </div>
    </div>
  );
}
