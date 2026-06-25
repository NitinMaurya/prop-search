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

/** Clean label: just "Sector N" (drops trailing road/area noise like ", Dadri Road"). */
export function sectorLabel(sector?: string | null): string {
  const n = sectorNum(sector);
  return n ? `Sector ${n}` : String(sector ?? "").trim();
}

/** Maps search by the sector NUMBER only (e.g. "Sector 47 Noida"), not the raw area. */
export function mapsUrl(sector?: string | null): string {
  const n = sectorNum(sector);
  const q = n ? `Sector ${n} Noida` : `${String(sector ?? "").trim()} Noida`;
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
