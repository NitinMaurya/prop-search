import { AMENITIES, DIR_ABBR, featureTags, hasFeatures } from "@/lib/tags";
import type { Match } from "@/lib/types";

/** Bare chip spans for the parsed labels — facing, floors, and any amenities (park,
 * basement, stilt, corner, lift); null if none. `dark` adapts them for the lightbox's
 * dark banner. Compact: 🧭 NE / 🏢 G+2 / 🌳 Park, with the full label on hover. */
export function FeatureChips({ m, dark = false }: { m: Match; dark?: boolean }) {
  const t = featureTags(m);
  if (!hasFeatures(m)) return null;
  const base = "text-xs font-semibold rounded-md px-2 py-1 whitespace-nowrap";
  const tone = dark ? "bg-white/10 text-white/80" : "bg-emerald-50 text-emerald-700";
  return (
    <>
      {t.facing && (
        <span title={`${t.facing} facing`} className={`${base} ${tone}`}>
          🧭 {DIR_ABBR[t.facing]}
        </span>
      )}
      {t.floors && (
        <span title={`${t.floors}`} className={`${base} ${tone}`}>🏢 {t.floors}</span>
      )}
      {t.road && (
        <span title={`${t.road} (approach road)`} className={`${base} ${tone}`}>🛣️ {t.road}</span>
      )}
      {AMENITIES.filter((a) => t[a.key]).map((a) => (
        <span key={a.key} title={a.label} className={`${base} ${tone}`}>
          {a.icon} {a.label}
        </span>
      ))}
    </>
  );
}

/** FeatureChips wrapped in a flex row (null if there are no labels), for the card/table. */
export function FeatureChipsRow({ m, className = "" }: { m: Match; className?: string }) {
  if (!hasFeatures(m)) return null;
  return (
    <div className={`flex flex-wrap gap-1.5 ${className}`}>
      <FeatureChips m={m} />
    </div>
  );
}
