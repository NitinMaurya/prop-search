export const CR = 10_000_000;

export function rupeesToCr(rupees?: number | null): string {
  if (!rupees) return "";
  const v = rupees / CR;
  return `₹ ${Number.isInteger(v) ? v : v.toFixed(2).replace(/\.?0+$/, "")} Cr`;
}

export function sectorNum(sector?: string | null): string | null {
  const m = String(sector ?? "").match(/\d+/);
  return m ? m[0] : null;
}

/** Sector number + block designator ("Block A" / "B Block"), ignoring road/area noise. */
function parseSector(sector?: string | null): { n: string | null; block: string | null; raw: string } {
  const raw = String(sector ?? "").trim();
  const bm = raw.match(/\bblock\s+([a-z0-9]{1,2})\b/i) || raw.match(/\b([a-z0-9]{1,2})\s+block\b/i);
  return { n: sectorNum(raw), block: bm ? bm[1].toUpperCase() : null, raw };
}

/** Clean label: "Sector N" plus a block if present ("Sector 50 · Block B"). */
export function sectorLabel(sector?: string | null): string {
  const { n, block, raw } = parseSector(sector);
  if (!n) return raw;
  return block ? `Sector ${n} · Block ${block}` : `Sector ${n}`;
}

/** Maps search by sector (+ block if present), e.g. "Sector 50 Block B Noida". */
export function mapsUrl(sector?: string | null): string {
  const { n, block, raw } = parseSector(sector);
  const q = n
    ? `Sector ${n}${block ? ` Block ${block}` : ""} Noida`
    : `${raw} Noida`;
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q)}`;
}

export function relativeTime(iso?: string | null): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const secs = Math.max(0, (Date.now() - then) / 1000);
  if (secs < 60) return "just now";
  for (const [unit, n] of [["day", 86400], ["hour", 3600], ["minute", 60]] as const) {
    if (secs >= n) {
      const v = Math.floor(secs / n);
      return `${v} ${unit}${v !== 1 ? "s" : ""} ago`;
    }
  }
  return "just now";
}
