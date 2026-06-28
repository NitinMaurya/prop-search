// Derived listing labels parsed from free text (title + description).
//
// Read-layer feature: no DB columns, no re-scrape. Surfaces two facts buyers scan for
// but portals bury in the blurb:
//   • facing direction  — "north facing", "facing north-east", "east-facing" -> "North-East"
//   • park-facing       — "overlooking the park", "facing a park", "park facing" -> true
//
// Mirror of the Python tags.py on the v1/Streamlit side. Kept deliberately small.

import type { Match } from "@/lib/types";

// Canonical labels in compass order — also the facing-filter options in the UI.
export const DIRECTIONS = [
  "North", "South", "East", "West",
  "North-East", "North-West", "South-East", "South-West",
] as const;
export type Direction = (typeof DIRECTIONS)[number];

// Short forms for compact chips/labels (N, NE, …).
export const DIR_ABBR: Record<Direction, string> = {
  "North": "N", "South": "S", "East": "E", "West": "W",
  "North-East": "NE", "North-West": "NW", "South-East": "SE", "South-West": "SW",
};

// Compound directions first so the alternation prefers them over the bare words inside.
const DIR = "north[\\s\\-/]?east|north[\\s\\-/]?west|south[\\s\\-/]?east|south[\\s\\-/]?west|north|south|east|west";

// "<dir> facing" or "facing <dir>".
const FACING_RE = new RegExp(`(?:(${DIR})[\\s\\-]*(?:facing|faced|face))|(?:facing[\\s:\\-]*(${DIR}))`, "i");

// "park facing", or a proximity word ("overlooking / facing / in front of / opposite /
// adjacent to …") followed within a few words by "park".
const PARK_RE = new RegExp(
  "park[\\s\\-]?facing" +
  "|(?:overlook(?:s|ing)?|facing|in\\s+front\\s+of|front\\s+of|opposite" +
  "|adjoining|adjacent\\s+to|abut(?:s|ting)?|next\\s+to|besides?)" +
  "\\s+(?:the\\s+|a\\s+)?(?:[a-z0-9]+\\s+){0,3}park",
  "i");

const COMPOUND: Record<string, Direction> = {
  northeast: "North-East", northwest: "North-West",
  southeast: "South-East", southwest: "South-West",
};
const SIMPLE: Record<string, Direction> = {
  north: "North", south: "South", east: "East", west: "West",
};

function canon(token: string): Direction | null {
  const t = token.toLowerCase().replace(/[\s\-/]/g, "");
  return COMPOUND[t] ?? SIMPLE[t] ?? null;
}

/** First compass direction described as the property's facing, or null. */
export function facing(text?: string | null): Direction | null {
  if (!text) return null;
  const m = FACING_RE.exec(text);
  if (!m) return null;
  return canon(m[1] || m[2]);
}

/** True if the text says the property faces / overlooks / fronts a park. */
export function parkFacing(text?: string | null): boolean {
  return !!text && PARK_RE.test(text);
}

const WORD_FLOORS: Record<string, number> = { single: 1, double: 2, triple: 3, four: 4 };

/** Floor layout stated in the text — "G+2", "3 floors", "double storey" — or null. */
export function floors(text?: string | null): string | null {
  if (!text) return null;
  let m = /\b(?:g|ground)\s*\+\s*(\d{1,2})\b/i.exec(text);          // "G+2" / "ground + 2"
  if (m) return `G+${m[1]}`;
  m = /\b(\d{1,2})\s*(?:storey|story|storied|floors?)\b/i.exec(text);  // "3 floors"
  if (m) return `${m[1]} floor${m[1] === "1" ? "" : "s"}`;
  m = /\b(single|double|triple|four)[\s-]*(?:storey|story|storied|floors?)\b/i.exec(text);
  if (m) { const n = WORD_FLOORS[m[1].toLowerCase()]; return `${n} floor${n === 1 ? "" : "s"}`; }
  return null;
}

const ROAD_UNIT = "m|mtr|mtrs|meter|meters|metre|metres|ft|feet";
// "<n> <unit> (wide) road" or "road (width/of) <n> <unit>" → normalized "30m road".
const ROAD_RE_A = new RegExp(
  `\\b(\\d{1,3}(?:\\.\\d+)?)\\s*(${ROAD_UNIT})\\b\\.?\\s*(?:wide\\s+)?(?:mtr\\.?\\s*)?road`, "i");
const ROAD_RE_B = new RegExp(
  `\\broad\\s*(?:width|of|is)?\\s*[:\\-]?\\s*(\\d{1,3}(?:\\.\\d+)?)\\s*(${ROAD_UNIT})\\b`, "i");

/** Approach-road width stated in the text — "30m road", "60ft road" — or null. */
export function roadWidth(text?: string | null): string | null {
  if (!text) return null;
  const m = ROAD_RE_A.exec(text) || ROAD_RE_B.exec(text);
  if (!m) return null;
  return `${m[1]}${/^f/i.test(m[2]) ? "ft" : "m"} road`;
}

// Boolean amenities parsed from the text. `key` is also the PropertyFeatures field and the
// URL filter token; the chip/checkbox show `icon` + `label`. Order = chip/filter order.
export const AMENITIES = [
  { key: "park", icon: "🌳", label: "Park", re: PARK_RE },
  { key: "basement", icon: "🔻", label: "Basement", re: /\bbasement\b/i },
  { key: "stilt", icon: "🚗", label: "Stilt", re: /\bstilt\b/i },
  { key: "corner", icon: "📐", label: "Corner", re: /\bcorner\b/i },
  { key: "lift", icon: "🛗", label: "Lift", re: /\b(?:lift|elevator)\b/i },
] as const;
export type AmenityKey = (typeof AMENITIES)[number]["key"];

export type PropertyFeatures = {
  facing: Direction | null;
  floors: string | null;
  road: string | null;
} & Record<AmenityKey, boolean>;

/** Derived labels for one match, parsed from its title + description. */
export function featureTags(m: Pick<Match, "title" | "description">): PropertyFeatures {
  const text = `${m.title ?? ""} ${m.description ?? ""}`;
  const out = { facing: facing(text), floors: floors(text), road: roadWidth(text) } as PropertyFeatures;
  for (const a of AMENITIES) out[a.key] = a.re.test(text);
  return out;
}

/** Whether a match has any derived feature label (for conditionally rendering chips). */
export function hasFeatures(m: Pick<Match, "title" | "description">): boolean {
  const t = featureTags(m);
  return !!t.facing || !!t.floors || !!t.road || AMENITIES.some((a) => t[a.key]);
}
