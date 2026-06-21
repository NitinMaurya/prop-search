"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { PageHeader } from "@/components/PageHeader";

export default function SystemPage() {
  const { data, isLoading } = useQuery({ queryKey: ["system"], queryFn: api.getSystem });

  return (
    <div>
      <PageHeader title="System" subtitle="Health of the unattended scrape pipeline." />
      {isLoading && <p className="text-[var(--color-muted)]">Loading…</p>}
      {data && (
        <>
          <div className="grid gap-3 mb-6" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px,1fr))" }}>
            <Tile label="Active listings" value={data.totals.active} tone="ok" />
            <Tile label="Stale listings" value={data.totals.stale} tone={data.totals.stale ? "warn" : "neutral"} />
          </div>

          <h2 className="text-xs font-bold uppercase tracking-wide text-[var(--color-muted)] mb-2">Portals</h2>
          <div className="grid gap-3 mb-6" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px,1fr))" }}>
            {data.portals.map((p) => (
              <div key={p.id} className="ps-card p-4">
                <div className="flex items-center justify-between">
                  <span className="font-bold">🌐 {p.name}</span>
                  <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${p.enabled ? "bg-green-100 text-green-700" : "bg-slate-100 text-slate-500"}`}>
                    {p.enabled ? "Enabled" : "Disabled"}
                  </span>
                </div>
                <div className="text-xs text-[var(--color-muted)] mt-2">Last run: {relativeTime(p.last_run_at)}</div>
              </div>
            ))}
          </div>

          <h2 className="text-xs font-bold uppercase tracking-wide text-[var(--color-muted)] mb-2">Run history</h2>
          <div className="ps-card overflow-x-auto">
            <table className="w-full text-sm whitespace-nowrap">
              <thead>
                <tr className="border-b-2 border-[var(--color-line)] text-left">
                  {["Started", "Finished", "Fetched", "Parsed", "Errors", "Matches", "Notified"].map((h) => (
                    <th key={h} className="px-4 py-3 font-bold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.runs.map((r) => (
                  <tr key={r.id} className="border-b border-[var(--color-line)] last:border-0">
                    <td className="px-4 py-2.5">{r.started_at?.replace("T", " ").slice(0, 16)}</td>
                    <td className="px-4 py-2.5 text-[var(--color-muted)]">{r.finished_at ? r.finished_at.replace("T", " ").slice(0, 16) : "running…"}</td>
                    <td className="px-4 py-2.5">{r.raw_fetched ?? 0}</td>
                    <td className="px-4 py-2.5">{r.parsed_ok ?? 0}</td>
                    <td className={`px-4 py-2.5 ${(r.parse_errors ?? 0) > 0 ? "text-red-600 font-bold" : "text-[var(--color-muted)]"}`}>{r.parse_errors ?? 0}</td>
                    <td className="px-4 py-2.5">{r.new_matches ?? 0}</td>
                    <td className="px-4 py-2.5">{r.notified ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function Tile({ label, value, tone }: { label: string; value: number; tone: "ok" | "warn" | "neutral" }) {
  const color = tone === "ok" ? "#059669" : tone === "warn" ? "#d97706" : "var(--color-ink)";
  return (
    <div className="ps-card p-4 border-l-4" style={{ borderLeftColor: color }}>
      <div className="text-xs font-bold uppercase tracking-wide text-[var(--color-muted)]">{label}</div>
      <div className="text-3xl font-black mt-1" style={{ color }}>{value}</div>
    </div>
  );
}
