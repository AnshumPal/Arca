import Link from "next/link";

// Three "product" cards — one per agent, in the lamp-catalogue style
const agents = [
  {
    id: "intake",
    code: "a01",
    name: "Intake",
    tagline: "For blending in — or standing out",
    description:
      "The intake agent takes its cue from the first contact: clear, conversational, unassuming. Refining and updating this approach with calibrated brevity, intake handles general questions and routes complex requests without ever putting itself in the limelight.",
    accent: "from-[#3a2a1a] to-[#1a0f08]",
    swatch: "#c87f4a",
  },
  {
    id: "research",
    code: "a02",
    name: "Research",
    tagline: "Anywhere, any depth",
    description:
      "Performing equally well at the surface and in the deep, the research agent is a pleasure to work with. Use it as a solitary piece to light up a single question, or in clusters above larger topics to add a jolt of insight, colour, and accent.",
    accent: "from-[#1f2a1a] to-[#0a120a]",
    swatch: "#6d7d5e",
  },
  {
    id: "action",
    code: "a03",
    name: "Action",
    tagline: "Get to the point",
    description:
      "The action agent executes specific tasks and returns structured, actionable output. Precise. If a task is ambiguous, it asks one clarifying question before proceeding — no posturing, no filler, just the work.",
    accent: "from-[#2a221a] to-[#120e08]",
    swatch: "#d4c4a8",
  },
];

export default function Home() {
  return (
    <div className="bg-[#050505] text-[#f5f1ea]">
      {/* ─── Hero ─────────────────────────────────────────── */}
      <section className="relative grain min-h-[80vh] flex flex-col justify-end px-8 pb-16 pt-32 md:px-16 md:pb-24 md:pt-40 border-b border-[#1a1a1a]">
        <div className="absolute top-8 right-8 md:top-12 md:right-16 flex items-center gap-3 text-xs uppercase tracking-[0.3em] text-[#8a8378]">
          <span className="h-px w-8 bg-[#c87f4a]" />
          a self-improving agent platform
        </div>

        <h1 className="display text-[14vw] md:text-[10vw] leading-[0.9] mb-8">
          Arca.
        </h1>

        <div className="max-w-2xl">
          <p className="text-lg md:text-xl text-[#8a8378] leading-relaxed mb-10">
            Three production agents serve live requests. The system observes
            every interaction, scores it across four dimensions, runs sandbox
            experiments in shadow mode, and proposes improvements — all without
            ever putting itself in the limelight, unless of course you want it to.
          </p>

          <div className="flex flex-wrap gap-3">
            <Link href="/chat" className="btn-primary">
              Open chat →
            </Link>
            <Link href="/dashboard" className="btn-secondary">
              View dashboard
            </Link>
          </div>
        </div>
      </section>

      {/* ─── Three agent cards ────────────────────────────── */}
      <section className="px-8 py-20 md:px-16 md:py-32">
        <div className="mb-16 flex items-end justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-[#8a8378] mb-3">
              The collection
            </p>
            <h2 className="display text-4xl md:text-5xl">Three agents</h2>
          </div>
          <Link href="/dashboard" className="text-sm text-[#8a8378] hover:text-[#f5f1ea]">
            Performance →
          </Link>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          {agents.map((a) => (
            <article
              key={a.id}
              className="group relative rounded-2xl border border-[#1a1a1a] overflow-hidden bg-[#0d0d0d] transition-all hover:border-[#2a2a2a]"
            >
              <div
                className={`aspect-[3/4] relative bg-gradient-to-br ${a.accent} grain overflow-hidden`}
              >
                {/* Abstract product mark — concentric circles in copper */}
                <div className="absolute inset-0 flex items-center justify-center">
                  <div
                    className="h-48 w-48 rounded-full border-2 opacity-80 transition-transform duration-700 group-hover:scale-110"
                    style={{ borderColor: a.swatch }}
                  >
                    <div
                      className="h-full w-full rounded-full border-2 scale-75"
                      style={{ borderColor: a.swatch, opacity: 0.6 }}
                    >
                      <div
                        className="h-full w-full rounded-full scale-50"
                        style={{ background: a.swatch, opacity: 0.9 }}
                      />
                    </div>
                  </div>
                </div>
                <div className="absolute top-4 left-4 right-4 flex items-start justify-between text-xs">
                  <span className="font-mono text-[#f5f1ea]/60">{a.code}</span>
                  <span className="text-[#f5f1ea]/60">/03</span>
                </div>
              </div>

              <div className="p-6">
                <h3 className="display text-2xl mb-1">{a.name}</h3>
                <p className="text-sm text-[#8a8378] mb-4">{a.tagline}</p>
                <p className="text-sm text-[#a8a09a] leading-relaxed">
                  {a.description}
                </p>
              </div>
            </article>
          ))}
        </div>
      </section>

      {/* ─── How it works ─────────────────────────────────── */}
      <section className="border-t border-[#1a1a1a] px-8 py-20 md:px-16 md:py-32">
        <p className="text-xs uppercase tracking-[0.3em] text-[#8a8378] mb-3">
          Method
        </p>
        <h2 className="display text-4xl md:text-5xl mb-16 max-w-3xl">
          Observe before you optimize.
          <br />
          <span className="text-[#8a8378]">Gate before you promote.</span>
        </h2>

        <div className="grid gap-12 md:grid-cols-2 lg:grid-cols-4">
          {[
            {
              n: "01",
              t: "Evaluate",
              d: "Every chat is scored automatically across latency, output length, user feedback, and error rate.",
            },
            {
              n: "02",
              t: "Shadow",
              d: "Experimental sandbox agents receive the same live traffic but never respond. Pure observation.",
            },
            {
              n: "03",
              t: "Optimize",
              d: "Every night the autoresearch loop reads 7 days of data and proposes improved prompts via LLM.",
            },
            {
              n: "04",
              t: "Promote",
              d: "A four-check gate (traces, delta, error floor, latency) advises. Only a human pressing approve makes it live.",
            },
          ].map((step) => (
            <div key={step.n}>
              <div className="text-xs font-mono text-[#c87f4a] mb-3">
                {step.n}
              </div>
              <h3 className="display text-2xl mb-3">{step.t}</h3>
              <p className="text-sm text-[#8a8378] leading-relaxed">{step.d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ─── Footer ───────────────────────────────────────── */}
      <footer className="border-t border-[#1a1a1a] px-8 py-12 md:px-16 flex flex-wrap items-center justify-between gap-4">
        <div className="text-xs text-[#5a5550]">
          Anshum Pal · 2026 · Arca v0.7.0
        </div>
        <div className="flex gap-6 text-xs">
          <a
            href="https://github.com/AnshumPal/Arca"
            target="_blank"
            rel="noreferrer"
            className="text-[#8a8378] hover:text-[#f5f1ea]"
          >
            GitHub
          </a>
          <a
            href="https://arca-pet9.onrender.com/docs"
            target="_blank"
            rel="noreferrer"
            className="text-[#8a8378] hover:text-[#f5f1ea]"
          >
            API docs
          </a>
        </div>
      </footer>
    </div>
  );
}
