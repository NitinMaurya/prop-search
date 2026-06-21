"use client";

import { useEffect, useState } from "react";
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
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    setCollapsed(localStorage.getItem("ps_sidebar_collapsed") === "1");
  }, []);

  const toggle = () => {
    setCollapsed((c) => {
      localStorage.setItem("ps_sidebar_collapsed", c ? "0" : "1");
      return !c;
    });
  };

  async function signOut() {
    await supabase.auth.signOut();
    router.replace("/login");
  }

  return (
    <aside className={`${collapsed ? "w-[68px]" : "w-60"} shrink-0 sticky top-0 h-screen self-start
      bg-[var(--color-surface)] border-r border-[var(--color-line)] p-3 flex flex-col
      transition-[width] duration-200`}>
      {/* brand + collapse toggle */}
      <div className="flex items-center gap-2.5 mb-3 min-h-9">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center text-lg ps-btn-grad shrink-0">🏡</div>
        {!collapsed && (
          <div className="min-w-0">
            <div className="text-lg font-extrabold leading-none bg-clip-text text-transparent truncate"
              style={{ backgroundImage: "var(--grad)" }}>prop-search</div>
            <div className="text-[11px] text-[var(--color-muted)] font-semibold mt-0.5">Noida kothi finder</div>
          </div>
        )}
        <button onClick={toggle} title={collapsed ? "Expand" : "Collapse"}
          className={`${collapsed ? "mx-auto mt-1" : "ml-auto"} text-[var(--color-muted)] hover:text-[var(--color-ink)] text-lg leading-none`}>
          {collapsed ? "»" : "«"}
        </button>
      </div>

      <div className="h-px bg-[var(--color-line)] mb-3" />

      <nav className="flex flex-col gap-0.5">
        {NAV.map((n) => {
          const active = pathname.startsWith(n.href);
          return (
            <Link key={n.href} href={n.href} title={collapsed ? n.label : undefined}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-xl font-semibold text-[15px] transition-colors ${
                collapsed ? "justify-center" : ""
              } ${active
                ? "text-[var(--color-brand-dk)] bg-[var(--color-brand-soft)]"
                : "text-[var(--color-ink)] hover:bg-[var(--color-brand-soft)]"}`}>
              <span className="text-lg leading-none">{n.icon}</span>
              {!collapsed && <span>{n.label}</span>}
            </Link>
          );
        })}
      </nav>

      <button onClick={signOut} title="Sign out"
        className={`mt-auto flex items-center gap-2 text-sm font-semibold text-[var(--color-muted)]
          hover:text-[var(--color-ink)] px-3 py-2 rounded-xl ${collapsed ? "justify-center" : ""}`}>
        <span>↩︎</span>{!collapsed && <span>Sign out</span>}
      </button>
    </aside>
  );
}
