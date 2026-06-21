"use client";

import { Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { sectorNum } from "@/lib/format";
import { useUrlState } from "@/lib/useUrlState";
import { MatchCard } from "@/components/MatchCard";
import { Lightbox } from "@/components/Lightbox";
import { PageHeader } from "@/components/PageHeader";
import { Loading } from "@/components/Loading";
import { Select, SORT_OPTIONS, sortMatches } from "@/components/Select";
import type { Match } from "@/lib/types";

const TABS = [
  { key: "liked", label: "👍 Liked" },
  { key: "passed", label: "👎 Passed" },
  { key: "followups", label: "📞 Follow-ups" },
];

export default function ShortlistPage() {
  return (
    <Suspense fallback={<Loading />}>
      <ShortlistInner />
    </Suspense>
  );
}

function groupBySector(rows: Match[]): [string, Match[]][] {
  const g = new Map<string, Match[]>();
  for (const m of rows) {
    const k = sectorNum(m.sector) ?? "—";
    (g.get(k) ?? g.set(k, []).get(k)!).push(m);
  }
  return [...g.entries()].sort((a, b) =>
    a[0] === "—" ? 1 : b[0] === "—" ? -1 : Number(a[0]) - Number(b[0]));
}

function ShortlistInner() {
  const { get, set } = useUrlState();
  const tab = get("tab", "liked");
  const setTab = (k: string) => set({ tab: k === "liked" ? null : k });
  const showCode = tab === "passed" ? "passed" : tab === "liked" ? "liked" : "all";

  const { data: rows = [], isLoading } = useQuery({
    queryKey: ["matches", showCode, "shortlist"],
    queryFn: () => api.listMatches({ show: showCode, sort: "best" }),
  });

  // follow-up filters (Matches-style, applied client-side to the curated set)
  const fsort = get("fsort", "best");
  const fsec = get("fsec", "");
  const fgroup = get("fgrp") === "1";

  const followupsAll = rows.filter((m) => m.verdict === "like" || m.contacted_at);
  const fuSectors = [...new Set(followupsAll.map((m) => sectorNum(m.sector)).filter(Boolean))]
    .sort((a, b) => Number(a) - Number(b)) as string[];
  let followups = fsec ? followupsAll.filter((m) => sectorNum(m.sector) === fsec) : followupsAll;
  followups = sortMatches(followups, fsort);
  const fuGroups = fgroup ? groupBySector(followups) : null;

  const imaged = rows.filter((m) => m.image_url);
  const idxOf = new Map(imaged.map((m, i) => [m.id, i] as const));
  const [lb, setLb] = useState<number | null>(null);

  const card = (m: Match, withNotes = false) => (
    <MatchCard key={m.match_id} m={m} enableNotes={withNotes}
      onZoom={idxOf.has(m.id) ? () => setLb(idxOf.get(m.id)!) : undefined} />
  );

  return (
    <div>
      <PageHeader title="Shortlist" subtitle="Homes you reacted to — liked, passed, and your follow-up notes." />
      <div className="flex gap-2 mb-5">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-4 py-2 rounded-xl font-bold text-sm ${
              tab === t.key ? "ps-btn-grad" : "border border-[var(--color-line)] text-[var(--color-muted)]"
            }`}>{t.label}</button>
        ))}
      </div>

      {isLoading ? <Loading /> : tab === "followups" ? (
        followupsAll.length === 0 ? (
          <Empty icon="📞" title="No follow-ups yet"
            sub="Like a listing or mark it Contacted — it shows up here to track." />
        ) : (
          <>
            <div className="flex flex-wrap items-end gap-3 mb-4">
              <Select label="Sort" value={fsort} onChange={(v) => set({ fsort: v === "best" ? null : v })}
                options={SORT_OPTIONS} />
              <Select label="Sector" value={fsec} onChange={(v) => set({ fsec: v })}
                options={[["", "All sectors"], ...fuSectors.map((s) => [s, `Sector ${s}`] as [string, string])]} />
              <label className="flex items-center gap-2 text-sm font-semibold text-[var(--color-muted)] pb-2">
                <input type="checkbox" checked={fgroup} onChange={(e) => set({ fgrp: e.target.checked ? "1" : null })} />
                🗂 Group by sector
              </label>
              <span className="ml-auto pb-2 text-sm text-[var(--color-muted)]">
                {followupsAll.filter((m) => m.contacted_at).length} contacted · {followupsAll.length} tracked
              </span>
            </div>
            {fuGroups ? (
              fuGroups.map(([sec, grp]) => (
                <section key={sec} className="mb-6">
                  <h2 className="text-lg font-extrabold border-b-2 border-[var(--color-line)] pb-2 mb-3 flex items-center gap-2">
                    📍 {sec === "—" ? "Other" : `Sector ${sec}`}
                    <span className="text-xs font-bold text-[var(--color-brand-dk)] bg-[var(--color-brand-soft)] rounded-full px-2.5 py-0.5">{grp.length}</span>
                  </h2>
                  <Grid>{grp.map((m) => card(m, true))}</Grid>
                </section>
              ))
            ) : <Grid>{followups.map((m) => card(m, true))}</Grid>}
          </>
        )
      ) : (
        <Grid>
          {rows.length === 0 && <Empty icon={tab === "liked" ? "💚" : "🗂️"} title={`Nothing ${tab} yet`} />}
          {rows.map((m) => card(m))}
        </Grid>
      )}

      <Lightbox items={imaged} index={lb} onIndex={setLb} onClose={() => setLb(null)} />
    </div>
  );
}

function Grid({ children }: { children: React.ReactNode }) {
  return <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%,320px),1fr))" }}>{children}</div>;
}

function Empty({ icon, title, sub }: { icon: string; title: string; sub?: string }) {
  return (
    <div className="ps-card p-12 text-center col-span-full">
      <div className="text-5xl mb-2">{icon}</div>
      <div className="text-lg font-bold">{title}</div>
      {sub && <p className="text-[var(--color-muted)] mt-1">{sub}</p>}
    </div>
  );
}
