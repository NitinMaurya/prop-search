"use client";

import { mapsUrl, rupeesToCr } from "@/lib/format";
import { PASS_REASONS, useMatchActions } from "@/lib/useMatchActions";
import type { Match } from "@/lib/types";

export function MatchCard({ m, onZoom }: { m: Match; onZoom?: () => void }) {
  const { feedback, contacted } = useMatchActions(m);
  const pct = m.score != null ? Math.round(m.score * 100) : null;
  const isContacted = !!m.contacted_at;

  return (
    <div className={`ps-card relative overflow-hidden flex flex-col h-full ${m.verdict === "nope" ? "opacity-60 hover:opacity-100" : ""}`}>
      {/* whole card opens the listing (stretched link); photo + actions sit above it */}
      {m.url && (
        <a href={m.url} target="_blank" rel="noopener" aria-label="Open listing"
          className="absolute inset-0 z-[1]" />
      )}
      {/* photo — FIXED height (not aspect) so image size can never change the card; never
          shrinks; object-cover crops to fill. Click to zoom (gallery). */}
      <div className="relative z-[2] shrink-0 h-[200px] bg-[var(--color-brand-soft)]">
        {m.image_url
          ? // eslint-disable-next-line @next/next/no-img-element
            <img src={m.image_url} alt="" onClick={onZoom}
              className={`w-full h-full object-cover block ${onZoom ? "cursor-zoom-in" : ""}`} />
          : <div className="w-full h-full flex items-center justify-center text-4xl opacity-50">🏠</div>}
        {m.is_new && (
          <span className="absolute top-2.5 left-2.5 text-xs font-extrabold text-white px-2.5 py-1 rounded-full"
            style={{ background: "linear-gradient(135deg,#10b981,#059669)" }}>🆕 New</span>
        )}
        <button onClick={() => contacted.mutate()}
          className={`absolute top-2.5 right-2.5 text-xs font-bold px-2.5 py-1.5 rounded-full border ${
            isContacted ? "bg-blue-600 text-white border-blue-600" : "bg-white/90 text-blue-600 border-white/70"
          }`}>
          {isContacted ? "✅ Contacted" : "📞 Contact"}{m.notes ? " 📝" : ""}
        </button>
        {m.sector && (
          <a href={mapsUrl(m.sector)} target="_blank" rel="noopener"
            className="absolute left-2.5 bottom-2.5 text-xs font-semibold text-white bg-black/70 rounded-lg px-2.5 py-1 flex items-center gap-1.5 no-underline hover:bg-blue-600/90">
            📍 {m.sector} 🗺️
          </a>
        )}
      </div>

      {/* body — fixed-height sections so every card is identical regardless of content.
          Text sits under the stretched link (so clicking it opens the listing); only the
          action buttons are raised above it. */}
      <div className="p-4 flex flex-col flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-2xl font-black tracking-tight text-[var(--color-ink)]">
            {rupeesToCr(m.price) || "On request"}
          </span>
          {m.size_sqm && (
            <span className="text-xs font-bold rounded-full px-3 py-1 bg-[var(--color-brand-soft)] text-[var(--color-brand)] shrink-0">
              {Math.round(m.size_sqm)} sqm
            </span>
          )}
        </div>
        <div className="text-sm font-semibold text-slate-700 mt-1 line-clamp-2 min-h-[2.5em]">
          {m.title ?? "Untitled listing"}
        </div>
        <p className="text-xs text-[var(--color-muted)] mt-1 line-clamp-2 min-h-[2.4em]">
          {m.description ?? ""}
        </p>

        <div className="mt-auto pt-3 flex items-center justify-between">
          <span className="text-xs text-[var(--color-muted)] font-semibold truncate">
            {m.owner ? `Req · ${m.owner}` : `Req #${m.requirement_id}`}
          </span>
          {pct != null && (
            <span className={`shrink-0 text-xs font-extrabold rounded-full px-2.5 py-1 ${
              pct >= 80 ? "bg-green-100 text-green-700"
                : pct >= 60 ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-600"
            }`}>{pct}% match</span>
          )}
        </div>

        <div className="relative z-[2] flex gap-2 mt-3">
          <button onClick={() => feedback.mutate({ v: "nope" })}
            className={`flex-1 py-2 rounded-xl font-bold text-sm border ${
              m.verdict === "nope" ? "bg-red-500 text-white border-red-500" : "text-red-600 border-red-200 hover:bg-red-50"
            }`}>👎 Pass</button>
          <button onClick={() => feedback.mutate({ v: "like" })}
            className={`flex-1 py-2 rounded-xl font-bold text-sm border ${
              m.verdict === "like" ? "bg-green-600 text-white border-green-600" : "text-green-600 border-green-200 hover:bg-green-50"
            }`}>👍 Like</button>
        </div>

        {/* pass reasons appear only when passed */}
        {m.verdict === "nope" && (
          <div className="relative z-[2] flex flex-wrap gap-1.5 mt-2.5">
            <span className="text-[11px] font-bold uppercase tracking-wide text-[var(--color-muted)] self-center">Why?</span>
            {PASS_REASONS.map(([code, label]) => (
              <button key={code} onClick={() => feedback.mutate({ v: "nope", reason: code })}
                className={`text-xs font-semibold px-2.5 py-1 rounded-full border whitespace-nowrap ${
                  m.pass_reason === code ? "bg-red-500 text-white border-red-500" : "bg-white border-[var(--color-line)] hover:border-red-300"
                }`}>{label}</button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
