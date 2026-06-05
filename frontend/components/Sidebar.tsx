"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const nav = [
  { href: "/",           label: "Home" },
  { href: "/chat",       label: "Chat" },
  { href: "/dashboard",  label: "Dashboard" },
  { href: "/sandboxes",  label: "Sandboxes" },
  { href: "/optimizer",  label: "Optimizer" },
  { href: "/promotions", label: "Promotions" },
  { href: "/versions",   label: "Versions" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-[#1a1a1a] bg-[#050505] px-6 py-8">
      <Link href="/" className="block mb-12">
        <div className="display text-2xl text-[#f5f1ea]">Arca</div>
        <div className="mt-1 text-[10px] uppercase tracking-[0.2em] text-[#8a8378]">
          v 0.7 — vault
        </div>
      </Link>

      <nav className="flex flex-col gap-1 text-sm">
        {nav.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`relative py-2 transition-colors ${
                active
                  ? "text-[#f5f1ea]"
                  : "text-[#8a8378] hover:text-[#f5f1ea]"
              }`}
            >
              {active && (
                <span className="absolute -left-6 top-1/2 -translate-y-1/2 h-1 w-1 rounded-full bg-[#c87f4a]" />
              )}
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto pt-8 text-xs text-[#5a5550] space-y-1">
        <a
          href="https://github.com/AnshumPal/Arca"
          className="hover:text-[#f5f1ea] block"
          target="_blank"
          rel="noreferrer"
        >
          GitHub →
        </a>
        <p>Anshum Pal · 2026</p>
      </div>
    </aside>
  );
}
