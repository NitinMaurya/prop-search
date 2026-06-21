"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

const NAV = [
  { href: "/matches", icon: "🎯", label: "Matches" },
  { href: "/shortlist", icon: "💚", label: "Shortlist" },
  { href: "/requirements", icon: "📋", label: "Requirements" },
  { href: "/system", icon: "🩺", label: "System" },
  { href: "/settings", icon: "⚙️", label: "Settings" },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  async function signOut() {
    await supabase.auth.signOut();
    router.replace("/login");
  }

  return (
    <aside className="w-60 shrink-0 min-h-screen bg-[var(--color-surface)] border-r border-[var(--color-line)] p-4 flex flex-col">
      <div className="flex items-center gap-2.5 mb-5">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center text-lg ps-btn-grad">🏡</div>
        <div>
          <div className="text-lg font-extrabold leading-none bg-clip-text text-transparent"
               style={{ backgroundImage: "var(--grad)" }}>prop-search</div>
          <div className="text-[11px] text-[var(--color-muted)] font-semibold mt-0.5">Noida kothi finder</div>
        </div>
      </div>
      <div className="h-px bg-[var(--color-line)] mb-3" />
      <nav className="flex flex-col gap-0.5">
        {NAV.map((n) => {
          const active = pathname.startsWith(n.href);
          return (
            <Link key={n.href} href={n.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-xl font-semibold text-[15px] transition-colors ${
                active
                  ? "text-[var(--color-brand-dk)] bg-[var(--color-brand-soft)]"
                  : "text-[var(--color-ink)] hover:bg-[var(--color-brand-soft)]"
              }`}>
              <span className="w-6 text-center text-lg">{n.icon}</span>
              <span>{n.label}</span>
            </Link>
          );
        })}
      </nav>
      <button onClick={signOut}
        className="mt-auto text-sm font-semibold text-[var(--color-muted)] hover:text-[var(--color-ink)] text-left px-3 py-2">
        ↩︎ Sign out
      </button>
    </aside>
  );
}
