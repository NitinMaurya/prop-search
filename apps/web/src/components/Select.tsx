export function Select({ label, value, onChange, options }: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
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

export const SORT_OPTIONS: [string, string][] = [
  ["best", "Best match"],
  ["price_asc", "Price ↑"],
  ["price_desc", "Price ↓"],
  ["size_asc", "Size ↑"],
  ["size_desc", "Size ↓"],
];

/** Client-side sort for already-fetched matches (Follow-ups filters locally). */
export function sortMatches<T extends { score?: number | null; price?: number | null; size_sqm?: number | null }>(
  rows: T[], code: string,
): T[] {
  const by = (sel: (m: T) => number | null | undefined, dir: 1 | -1) =>
    [...rows].sort((a, b) => {
      const av = sel(a), bv = sel(b);
      if (av == null) return 1;
      if (bv == null) return -1;
      return (av - bv) * dir;
    });
  switch (code) {
    case "price_asc": return by((m) => m.price, 1);
    case "price_desc": return by((m) => m.price, -1);
    case "size_asc": return by((m) => m.size_sqm, 1);
    case "size_desc": return by((m) => m.size_sqm, -1);
    default: return by((m) => m.score, -1);
  }
}
