"use client";

import { Suspense, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { sectorNum } from "@/lib/format";
import { AMENITIES, DIRECTIONS, DIR_ABBR, featureTags } from "@/lib/tags";
import { useUrlState } from "@/lib/useUrlState";
import type { Match } from "@/lib/types";
import { MatchCard } from "@/components/MatchCard";
import { MatchTable } from "@/components/MatchTable";
import { Lightbox } from "@/components/Lightbox";
import { PageHeader } from "@/components/PageHeader";
import { Select } from "@/components/Select";
import { MultiSelect } from "@/components/MultiSelect";
import { SkeletonCards } from "@/components/Loading";

const SHOW = [
  { code: "liked_new", label: "👍 Liked & new" },
  { code: "liked", label: "👍 Liked" },
  { code: "unrated", label: "🆕 Unrated" },
  { code: "passed", label: "👎 Passed" },
  { code: "all", label: "All" },
];
const SORT = [
  { code: "best", label: "Best match" },
  { code: "price_asc", label: "Price ↑" },
  { code: "price_desc", label: "Price ↓" },
  { code: "size_asc", label: "Size ↑" },
  { code: "size_desc", label: "Size ↓" },
];

export default function MatchesPage() {
  return (
    <Suspense fallback={<SkeletonCards />}>
      <MatchesInner />
    </Suspense>
  );
}

function MatchesInner() {
  const { get, set } = useUrlState();
  const show = get("show", "liked_new");
  const sort = get("sort", "best");
  const sector = get("sec", "");
  const facing = get("face", "");
  const amen = new Set(get("amen", "").split(",").filter(Boolean));  // required amenities
  const road = new Set(get("road", "").split(",").filter(Boolean));  // any of these road widths
  const group = get("grp") === "1";
  const view = get("view") === "table" ? "table" : "cards";

  const setShow = (v: string) => set({ show: v === "liked_new" ? null : v });
  const setSort = (v: string) => set({ sort: v === "best" ? null : v });
  const setSector = (v: string) => set({ sec: v });
  const setFacing = (v: string) => set({ face: v || null });
  const toggleAmen = (key: string, on: boolean) => {
    const next = new Set(amen);
    if (on) next.add(key); else next.delete(key);
    set({ amen: [...next].join(",") || null });
  };
  const toggleRoad = (value: string, on: boolean) => {
    const next = new Set(road);
    if (on) next.add(value); else next.delete(value);
    set({ road: [...next].join(",") || null });
  };
  const setGroup = (on: boolean) => set({ grp: on ? "1" : null });
  const setView = (v: string) => set({ view: v === "cards" ? null : v });

  const { data: matches = [], isLoading, error } = useQuery({
    queryKey: ["matches", show, sort, sector],
    queryFn: () => api.listMatches({ show, sort, sectors: sector }),
  });

  const sectorOpts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const m of matches) {
      const n = sectorNum(m.sector);
      if (n) counts.set(n, (counts.get(n) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => Number(a[0]) - Number(b[0]));
  }, [matches]);

  // Facing + amenity options, derived from the description (tags.ts). Built from the full
  // server-filtered set so options/counts stay stable when one is selected.
  const facingOpts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const m of matches) {
      const f = featureTags(m).facing;
      if (f) counts.set(f, (counts.get(f) ?? 0) + 1);
    }
    return DIRECTIONS.filter((d) => counts.has(d))
      .map((d) => [d, counts.get(d)!] as [string, number]);
  }, [matches]);
  const amenityOpts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const m of matches) {
      const t = featureTags(m);
      for (const a of AMENITIES) if (t[a.key]) counts.set(a.key, (counts.get(a.key) ?? 0) + 1);
    }
    return AMENITIES.filter((a) => counts.has(a.key))
      .map((a) => ({ ...a, count: counts.get(a.key)! }));
  }, [matches]);
  const roadOpts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const m of matches) {
      const r = featureTags(m).road;
      if (r) counts.set(r, (counts.get(r) ?? 0) + 1);
    }
    const meters = (label: string) => {  // sort by width; ft → m so units interleave
      const mm = /^(\d+(?:\.\d+)?)(m|ft)/.exec(label);
      return mm ? parseFloat(mm[1]) * (mm[2] === "ft" ? 0.3048 : 1) : 0;
    };
    return [...counts.entries()].sort((a, b) => meters(a[0]) - meters(b[0]))
      .map(([value, count]) => ({ value, count }));
  }, [matches]);

  // Facing / amenity / road filters are client-side (labels aren't stored — see tags.ts).
  // Amenities are AND (every checked one); road widths are OR (any selected width).
  const filtered = useMemo(() => matches.filter((m) => {
    const t = featureTags(m);
    if (facing && t.facing !== facing) return false;
    for (const key of amen) if (!t[key as keyof typeof t]) return false;
    if (road.size && (!t.road || !road.has(t.road))) return false;
    return true;
  }), [matches, facing, amen, road]);

  const groups = useMemo(() => {
    if (!group) return null;
    const g = new Map<string, typeof filtered>();
    for (const m of filtered) {
      const k = sectorNum(m.sector) ?? "—";
      (g.get(k) ?? g.set(k, []).get(k)!).push(m);
    }
    return [...g.entries()].sort((a, b) =>
      a[0] === "—" ? 1 : b[0] === "—" ? -1 : Number(a[0]) - Number(b[0]));
  }, [group, filtered]);

  // The lightbox doubles as the full-details view, so it covers ALL listings (not just
  // ones with a photo) — imageless cards open it via the placeholder too.
  const gallery = filtered;
  const idxOf = useMemo(() => {
    const mp = new Map<number, number>();
    gallery.forEach((m, i) => mp.set(m.id, i));
    return mp;
  }, [gallery]);
  const [lb, setLb] = useState<number | null>(null);

  const zoom = (id: number) => { if (idxOf.has(id)) setLb(idxOf.get(id)!); };
  const renderBlock = (rows: Match[]) =>
    view === "table"
      ? <MatchTable rows={rows} onZoom={zoom} />
      : <Grid>{rows.map((m) => (
          <MatchCard key={m.match_id} m={m} onZoom={() => zoom(m.id)} />
        ))}</Grid>;

  return (
    <div>
      <div className="flex items-start justify-between gap-4">
        <PageHeader title="Matches" subtitle="Listings ranked by how well they fit your requirements." />
        <div className="flex rounded-xl border border-[var(--color-line)] overflow-hidden shrink-0 mt-1">
          {(["cards", "table"] as const).map((v) => (
            <button key={v} onClick={() => setView(v)}
              className={`px-3.5 py-2 text-sm font-bold ${view === v ? "ps-btn-grad" : "text-[var(--color-muted)] hover:bg-slate-50"}`}>
              {v === "cards" ? "▦ Cards" : "☰ Table"}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3 mb-5">
        <Select label="Show" value={show} onChange={setShow}
          options={SHOW.map((s) => [s.code, s.label])} />
        <Select label="Sort" value={sort} onChange={setSort}
          options={SORT.map((s) => [s.code, s.label])} />
        <Select label="Sector" value={sector} onChange={setSector}
          options={[["", "All sectors"], ...sectorOpts.map(([n, c]) => [n, `Sector ${n} (${c})`] as [string, string])]} />
        {facingOpts.length > 0 && (
          <Select label="🧭 Facing" value={facing} onChange={setFacing}
            options={[["", "Any facing"], ...facingOpts.map(([d, c]) => [d, `${DIR_ABBR[d as keyof typeof DIR_ABBR]} (${c})`] as [string, string])]} />
        )}
        {amenityOpts.length > 0 && (
          <MultiSelect label="✨ Features" placeholder="Any feature"
            selected={amen} onToggle={toggleAmen}
            options={amenityOpts.map((a) => ({
              value: a.key, label: `${a.icon} ${a.label}`, count: a.count }))} />
        )}
        {roadOpts.length > 0 && (
          <MultiSelect label="🛣️ Road" placeholder="Any road"
            selected={road} onToggle={toggleRoad}
            options={roadOpts.map((r) => ({
              value: r.value, label: r.value.replace(/ road$/, ""), count: r.count }))} />
        )}
        <label className="flex items-center gap-2 text-sm font-semibold text-[var(--color-muted)] pb-2">
          <input type="checkbox" checked={group} onChange={(e) => setGroup(e.target.checked)} />
          🗂 Group by sector
        </label>
      </div>

      {isLoading && <SkeletonCards />}
      {error && <p className="text-red-600 text-sm">Couldn’t load matches: {(error as Error).message}</p>}
      {!isLoading && !filtered.length && (
        <div className="ps-card p-12 text-center">
          <div className="text-5xl mb-2">🔍</div>
          <div className="text-lg font-bold">No matches for these filters</div>
          <p className="text-[var(--color-muted)] mt-1">Try “All” under Show, or add a requirement.</p>
        </div>
      )}

      {!isLoading && filtered.length > 0 && (groups ? (
        groups.map(([sec, rows]) => (
          <section key={sec} className="mb-6">
            <h2 className="text-lg font-extrabold border-b-2 border-[var(--color-line)] pb-2 mb-3 flex items-center gap-2">
              📍 {sec === "—" ? "Other" : `Sector ${sec}`}
              <span className="text-xs font-bold text-[var(--color-brand-dk)] bg-[var(--color-brand-soft)] rounded-full px-2.5 py-0.5">{rows.length}</span>
            </h2>
            {renderBlock(rows)}
          </section>
        ))
      ) : renderBlock(filtered))}

      <Lightbox items={gallery} index={lb} onIndex={setLb} onClose={() => setLb(null)} />
    </div>
  );
}

function Grid({ children }: { children: React.ReactNode }) {
  return <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%,320px),1fr))" }}>{children}</div>;
}
