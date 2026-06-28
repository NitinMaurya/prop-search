"use client";

import { Suspense, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { sectorNum } from "@/lib/format";
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
  sectors: string[]; // distinct sector numbers this agent has listings in
}

function groupByAgent(rows: Match[]): AgentGroup[] {
  const g = new Map<string, AgentGroup>();
  const secs = new Map<string, Set<string>>();
  for (const m of rows) {
    const key = agentName(m.advertiser);
    const grp = g.get(key) ?? g.set(key, { key, listings: [], contacted: 0, sectors: [] }).get(key)!;
    grp.listings.push(m);
    if (m.contacted_at) grp.contacted += 1;
    const s = sectorNum(m.sector);
    if (s) (secs.get(key) ?? secs.set(key, new Set()).get(key)!).add(s);
  }
  for (const grp of g.values())
    grp.sectors = [...(secs.get(grp.key) ?? [])].sort((a, b) => Number(a) - Number(b));
  return [...g.values()];
}

/** Agent is "blacklisted" when every one of their listings is passed via the agent reason. */
function isBlacklisted(a: AgentGroup): boolean {
  return a.listings.length > 0 &&
    a.listings.every((m) => m.verdict === "nope" && m.pass_reason === "agent");
}

/** Split an agent's listings into per-sector sections (unknown sector last). */
function groupBySector(rows: Match[]): [string, Match[]][] {
  const g = new Map<string, Match[]>();
  for (const m of rows) {
    const k = sectorNum(m.sector) ?? "—";
    (g.get(k) ?? g.set(k, []).get(k)!).push(m);
  }
  return [...g.entries()].sort((a, b) =>
    a[0] === "—" ? 1 : b[0] === "—" ? -1 : Number(a[0]) - Number(b[0]));
}

const SORTS: [string, string][] = [
  ["count", "Most listings"],
  ["uncontacted", "Not contacted first"],
  ["name", "Name (A–Z)"],
];

const CONTACT_FILTER: [string, string][] = [
  ["all", "All agents"],
  ["contacted", "Contacted"],
  ["uncontacted", "Not contacted"],
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
  const cf = get("cf", "all");          // contacted filter: all | contacted | uncontacted
  const groupSec = get("grp") === "1";  // group each agent's listings by sector

  // Every matched listing (regardless of like/pass) so the per-agent counts are complete.
  const { data: rows = [], isLoading } = useQuery({
    queryKey: ["matches", "all", "agents"],
    queryFn: () => api.listMatches({ show: "all", sort: "best" }),
  });

  const qc = useQueryClient();
  // Blacklist = pass all the agent's listings with the "agent" reason; restore = un-pass
  // those. We only touch listings that need it, so a manual pass on one listing survives.
  const blacklist = useMutation({
    mutationFn: async ({ group, on }: { group: AgentGroup; on: boolean }) => {
      const targets = group.listings.filter((m) =>
        on
          ? !(m.verdict === "nope" && m.pass_reason === "agent")
          : m.verdict === "nope" && m.pass_reason === "agent");
      await Promise.all(
        targets.map((m) =>
          on ? api.setFeedback(m.id, "nope", "agent") : api.setFeedback(m.id, "nope")));
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["matches"] }),
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

  const card = (m: Match) => (
    <MatchCard key={m.match_id} m={m} enableNotes
      onZoom={idxOf.has(m.id) ? () => setLb(idxOf.get(m.id)!) : undefined} />
  );

  const allGroups = groupByAgent(rows);
  const totalContactedAgents = allGroups.filter((a) => a.contacted > 0).length;
  let groups = allGroups;
  if (cf === "contacted") groups = groups.filter((a) => a.contacted > 0);
  else if (cf === "uncontacted") groups = groups.filter((a) => a.contacted === 0);
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
            <Tile label="Agents" value={allGroups.length} />
            <Tile label="Listings" value={rows.length} />
            <Tile label="Contacted" value={`${totalContactedAgents}/${allGroups.length}`} />
          </div>

          {/* controls */}
          <div className="flex flex-wrap items-end gap-3 mb-4">
            <Select label="Sort" value={sort} onChange={(v) => set({ sort: v === "count" ? null : v })}
              options={SORTS} />
            <Select label="Contacted" value={cf} onChange={(v) => set({ cf: v === "all" ? null : v })}
              options={CONTACT_FILTER} />
            <label className="flex flex-col gap-1">
              <span className="text-xs font-bold text-[var(--color-muted)] uppercase tracking-wide">Search</span>
              <input value={q} onChange={(e) => set({ q: e.target.value || null })}
                placeholder="Agent name…"
                className="px-3 py-2 rounded-xl border border-[var(--color-line)] bg-[var(--color-surface)] text-sm font-semibold w-56" />
            </label>
            <label className="flex items-center gap-2 text-sm font-semibold text-[var(--color-muted)] pb-2">
              <input type="checkbox" checked={groupSec}
                onChange={(e) => set({ grp: e.target.checked ? "1" : null })} />
              🗂 Group listings by sector
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
              const bl = isBlacklisted(a);
              return (
                <div key={a.key} className={`ps-card overflow-hidden ${bl ? "opacity-70" : ""}`}>
                  <div onClick={() => toggle(a.key)}
                    className="w-full cursor-pointer px-4 py-3 hover:bg-[var(--color-brand-soft)] transition-colors">
                    <div className="flex items-center gap-3">
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
                      {bl && (
                        <span className="text-xs font-bold rounded-full px-2.5 py-0.5 shrink-0 text-red-700 bg-red-100">
                          🚫 Blacklisted
                        </span>
                      )}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          const ok = bl || window.confirm(
                            `Blacklist ${a.key}? All ${n} listing${n === 1 ? "" : "s"} will be marked Passed.`);
                          if (ok) blacklist.mutate({ group: a, on: !bl });
                        }}
                        disabled={blacklist.isPending}
                        className={`text-xs font-bold px-3 py-1.5 rounded-full border shrink-0 disabled:opacity-50 ${
                          bl ? "border-[var(--color-line)] text-[var(--color-muted)] hover:bg-[var(--color-brand-soft)]"
                             : "border-red-200 text-red-600 hover:bg-red-50"
                        }`}>
                        {bl ? "↩︎ Restore" : "🚫 Blacklist"}
                      </button>
                    </div>
                    {a.sectors.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1.5 mt-2 pl-7">
                        <span className="text-[11px] font-bold uppercase tracking-wide text-[var(--color-muted)]">Sectors</span>
                        {a.sectors.map((s) => (
                          <span key={s} className="text-xs font-semibold text-[var(--color-brand-dk)] bg-[var(--color-brand-soft)] rounded-full px-2 py-0.5">
                            {s}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  {isOpen && (
                    <div className="p-4 border-t border-[var(--color-line)]">
                      {groupSec ? (
                        groupBySector(a.listings).map(([sec, grp]) => (
                          <section key={sec} className="mb-5 last:mb-0">
                            <h3 className="text-sm font-extrabold text-[var(--color-ink)] mb-2 flex items-center gap-2">
                              📍 {sec === "—" ? "Other" : `Sector ${sec}`}
                              <span className="text-xs font-bold text-[var(--color-brand-dk)] bg-[var(--color-brand-soft)] rounded-full px-2 py-0.5">{grp.length}</span>
                            </h3>
                            <Grid>{grp.map(card)}</Grid>
                          </section>
                        ))
                      ) : (
                        <Grid>{a.listings.map(card)}</Grid>
                      )}
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
