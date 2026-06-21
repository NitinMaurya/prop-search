"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { sectorNum } from "@/lib/format";
import { MatchCard } from "@/components/MatchCard";
import { PageHeader } from "@/components/PageHeader";

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
  const [show, setShow] = useState("liked_new");
  const [sort, setSort] = useState("best");
  const [sector, setSector] = useState("");
  const [group, setGroup] = useState(false);

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

  const groups = useMemo(() => {
    if (!group) return null;
    const g = new Map<string, typeof matches>();
    for (const m of matches) {
      const k = sectorNum(m.sector) ?? "—";
      (g.get(k) ?? g.set(k, []).get(k)!).push(m);
    }
    return [...g.entries()].sort((a, b) =>
      a[0] === "—" ? 1 : b[0] === "—" ? -1 : Number(a[0]) - Number(b[0]));
  }, [group, matches]);

  return (
    <div>
      <PageHeader title="Matches" subtitle="Listings ranked by how well they fit your requirements." />

      <div className="flex flex-wrap items-end gap-3 mb-5">
        <Select label="Show" value={show} onChange={setShow}
          options={SHOW.map((s) => [s.code, s.label])} />
        <Select label="Sort" value={sort} onChange={setSort}
          options={SORT.map((s) => [s.code, s.label])} />
        <Select label="Sector" value={sector} onChange={setSector}
          options={[["", "All sectors"], ...sectorOpts.map(([n, c]) => [n, `Sector ${n} (${c})`] as [string, string])]} />
        <label className="flex items-center gap-2 text-sm font-semibold text-[var(--color-muted)] pb-2">
          <input type="checkbox" checked={group} onChange={(e) => setGroup(e.target.checked)} />
          🗂 Group by sector
        </label>
      </div>

      {isLoading && <p className="text-[var(--color-muted)]">Loading…</p>}
      {error && <p className="text-red-600 text-sm">Couldn’t load matches: {(error as Error).message}</p>}
      {!isLoading && !matches.length && (
        <div className="ps-card p-12 text-center">
          <div className="text-5xl mb-2">🔍</div>
          <div className="text-lg font-bold">No matches for these filters</div>
          <p className="text-[var(--color-muted)] mt-1">Try “All” under Show, or add a requirement.</p>
        </div>
      )}

      {groups ? (
        groups.map(([sec, rows]) => (
          <section key={sec} className="mb-6">
            <h2 className="text-lg font-extrabold border-b-2 border-[var(--color-line)] pb-2 mb-3 flex items-center gap-2">
              📍 {sec === "—" ? "Other" : `Sector ${sec}`}
              <span className="text-xs font-bold text-[var(--color-brand-dk)] bg-[var(--color-brand-soft)] rounded-full px-2.5 py-0.5">{rows.length}</span>
            </h2>
            <Grid>{rows.map((m) => <MatchCard key={m.match_id} m={m} />)}</Grid>
          </section>
        ))
      ) : (
        <Grid>{matches.map((m) => <MatchCard key={m.match_id} m={m} />)}</Grid>
      )}
    </div>
  );
}

function Grid({ children }: { children: React.ReactNode }) {
  return <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%,290px),1fr))" }}>{children}</div>;
}

function Select({ label, value, onChange, options }: {
  label: string; value: string; onChange: (v: string) => void; options: [string, string][];
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-bold uppercase tracking-wide text-[var(--color-muted)]">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="rounded-xl border border-[var(--color-line)] bg-white px-3 py-2 text-sm font-semibold outline-none focus:border-[var(--color-brand)]">
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  );
}
