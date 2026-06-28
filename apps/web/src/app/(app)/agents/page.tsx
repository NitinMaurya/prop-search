"use client";

import { Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useUrlState } from "@/lib/useUrlState";
import { MatchCard } from "@/components/MatchCard";
import { Lightbox } from "@/components/Lightbox";
import { PageHeader } from "@/components/PageHeader";
import { Loading } from "@/components/Loading";
import { Select } from "@/components/Select";
import type { Match } from "@/lib/types";

/** The agent who posted a listing. `advertiser` is stored as "Name · Role"
 * (e.g. "Viewpoint Realtors · Agent") — group by the name only so an agent isn't
 * split across their Agent / Owner / Dealer label. */
function agentName(advertiser?: string | null): string {
  const a = (advertiser ?? "").trim();
  if (!a) return "Unknown agent";
  const i = a.indexOf(" · ");
  return (i >= 0 ? a.slice(0, i).trim() : a) || "Unknown agent";
}

interface AgentGroup {
  key: string;
  listings: Match[];
  contacted: number; // how many of this agent's listings you've contacted
}

function groupByAgent(rows: Match[]): AgentGroup[] {
  const g = new Map<string, AgentGroup>();
  for (const m of rows) {
    const key = agentName(m.advertiser);
    const grp = g.get(key) ?? g.set(key, { key, listings: [], contacted: 0 }).get(key)!;
    grp.listings.push(m);
    if (m.contacted_at) grp.contacted += 1;
  }
  return [...g.values()];
}

const SORTS: [string, string][] = [
  ["count", "Most listings"],
  ["uncontacted", "Not contacted first"],
  ["name", "Name (A–Z)"],
];

function sortAgents(groups: AgentGroup[], code: string): AgentGroup[] {
  const byCount = (a: AgentGroup, b: AgentGroup) =>
    b.listings.length - a.listings.length || a.key.localeCompare(b.key);
  if (code === "name") return [...groups].sort((a, b) => a.key.localeCompare(b.key));
  if (code === "uncontacted")
    return [...groups].sort(
      (a, b) => Number(a.contacted > 0) - Number(b.contacted > 0) || byCount(a, b));
  return [...groups].sort(byCount);
}

export default function AgentsPage() {
  return (
    <Suspense fallback={<Loading />}>
      <AgentsInner />
    </Suspense>
  );
}

function AgentsInner() {
  const { get, set } = useUrlState();
  const sort = get("sort", "count");
  const q = get("q", "");

  // Every matched listing (regardless of like/pass) so the per-agent counts are complete.
  const { data: rows = [], isLoading } = useQuery({
    queryKey: ["matches", "all", "agents"],
    queryFn: () => api.listMatches({ show: "all", sort: "best" }),
  });

  // Lightbox spans ALL listings so prev/next walks across agents.
  const imaged = rows.filter((m) => m.image_url);
  const idxOf = new Map(imaged.map((m, i) => [m.id, i] as const));
  const [lb, setLb] = useState<number | null>(null);

  const [open, setOpen] = useState<Set<string>>(new Set());
  const toggle = (k: string) =>
    setOpen((s) => {
      const n = new Set(s);
      if (n.has(k)) n.delete(k);
      else n.add(k);
      return n;
    });

  let groups = groupByAgent(rows);
  const totalContactedAgents = groups.filter((a) => a.contacted > 0).length;
  if (q.trim())
    groups = groups.filter((a) => a.key.toLowerCase().includes(q.trim().toLowerCase()));
  groups = sortAgents(groups, sort);

  return (
    <div>
      <PageHeader
        title="Agents"
        subtitle="Your matched listings grouped by the agent who posted them — how many each has, and whether you've contacted them."
      />

      {isLoading ? (
        <Loading />
      ) : rows.length === 0 ? (
        <Empty icon="🧑‍💼" title="No agents yet"
          sub="Once listings match your requirements, the agents who posted them collect here." />
      ) : (
        <>
          {/* summary tiles */}
          <div className="grid grid-cols-3 gap-3 mb-5 max-w-md">
            <Tile label="Agents" value={groupByAgent(rows).length} />
            <Tile label="Listings" value={rows.length} />
            <Tile label="Contacted" value={`${totalContactedAgents}/${groupByAgent(rows).length}`} />
          </div>

          {/* controls */}
          <div className="flex flex-wrap items-end gap-3 mb-4">
            <Select label="Sort" value={sort} onChange={(v) => set({ sort: v === "count" ? null : v })}
              options={SORTS} />
            <label className="flex flex-col gap-1">
              <span className="text-xs font-bold text-[var(--color-muted)] uppercase tracking-wide">Search</span>
              <input value={q} onChange={(e) => set({ q: e.target.value || null })}
                placeholder="Agent name…"
                className="px-3 py-2 rounded-xl border border-[var(--color-line)] bg-[var(--color-surface)] text-sm font-semibold w-56" />
            </label>
            <span className="ml-auto pb-2 text-sm text-[var(--color-muted)]">
              {groups.length} agent{groups.length === 1 ? "" : "s"} shown
            </span>
          </div>

          {/* agent rows */}
          <div className="flex flex-col gap-2.5">
            {groups.map((a) => {
              const isOpen = open.has(a.key);
              const n = a.listings.length;
              const done = a.contacted > 0;
              return (
                <div key={a.key} className="ps-card overflow-hidden">
                  <button onClick={() => toggle(a.key)}
                    className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[var(--color-brand-soft)] transition-colors">
                    <span className="text-[var(--color-muted)] text-xs w-4">{isOpen ? "▼" : "▶"}</span>
                    <span className="text-lg">🧑‍💼</span>
                    <span className="font-extrabold truncate flex-1">{a.key}</span>
                    <span className="text-xs font-bold text-[var(--color-brand-dk)] bg-[var(--color-brand-soft)] rounded-full px-2.5 py-0.5 shrink-0">
                      {n} listing{n === 1 ? "" : "s"}
                    </span>
                    <span className={`text-xs font-bold rounded-full px-2.5 py-0.5 shrink-0 ${
                      done ? "text-green-700 bg-green-100" : "text-amber-700 bg-amber-100"
                    }`}>
                      {done ? `✅ ${a.contacted}/${n} contacted` : "📭 not contacted"}
                    </span>
                  </button>
                  {isOpen && (
                    <div className="p-4 border-t border-[var(--color-line)]">
                      <Grid>
                        {a.listings.map((m) => (
                          <MatchCard key={m.match_id} m={m} enableNotes
                            onZoom={idxOf.has(m.id) ? () => setLb(idxOf.get(m.id)!) : undefined} />
                        ))}
                      </Grid>
                    </div>
                  )}
                </div>
              );
            })}
            {groups.length === 0 && (
              <Empty icon="🔍" title="No agents match that search" />
            )}
          </div>
        </>
      )}

      <Lightbox items={imaged} index={lb} onIndex={setLb} onClose={() => setLb(null)} />
    </div>
  );
}

function Tile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="ps-card px-4 py-3">
      <div className="text-xs font-bold text-[var(--color-muted)] uppercase tracking-wide">{label}</div>
      <div className="text-2xl font-extrabold text-[var(--color-ink)] mt-0.5">{value}</div>
    </div>
  );
}

function Grid({ children }: { children: React.ReactNode }) {
  return <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%,320px),1fr))" }}>{children}</div>;
}

function Empty({ icon, title, sub }: { icon: string; title: string; sub?: string }) {
  return (
    <div className="ps-card p-12 text-center">
      <div className="text-5xl mb-2">{icon}</div>
      <div className="text-lg font-bold">{title}</div>
      {sub && <p className="text-[var(--color-muted)] mt-1">{sub}</p>}
    </div>
  );
}
