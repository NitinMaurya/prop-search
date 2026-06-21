"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { mapsUrl, rupeesToCr } from "@/lib/format";
import type { Match } from "@/lib/types";

export function MatchCard({ m }: { m: Match }) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["matches"] });

  const feedback = useMutation({
    mutationFn: (v: "like" | "nope") => api.setFeedback(m.id, v),
    onSuccess: invalidate,
  });
  const contacted = useMutation({
    mutationFn: () => api.setContacted(m.id),
    onSuccess: invalidate,
  });

  const pct = m.score != null ? Math.round(m.score * 100) : null;
  const isContacted = !!m.contacted_at;

  return (
    <div className={`ps-card overflow-hidden flex flex-col ${m.verdict === "nope" ? "opacity-60" : ""}`}>
      <div className="relative aspect-[16/10] bg-[var(--color-brand-soft)]">
        {m.image_url
          ? // eslint-disable-next-line @next/next/no-img-element
            <img src={m.image_url} alt="" className="w-full h-full object-cover" />
          : <div className="w-full h-full flex items-center justify-center text-4xl opacity-50">🏠</div>}
        {m.is_new && (
          <span className="absolute top-2.5 left-2.5 text-xs font-extrabold text-white px-2.5 py-1 rounded-full"
            style={{ background: "linear-gradient(135deg,#10b981,#059669)" }}>🆕 New</span>
        )}
        <button onClick={() => contacted.mutate()}
          className={`absolute top-2.5 right-2.5 text-xs font-bold px-2.5 py-1.5 rounded-full border ${
            isContacted ? "bg-blue-600 text-white border-blue-600" : "bg-white/90 text-blue-600 border-white/70"
          }`}>
          {isContacted ? "✅ Contacted" : "📞 Contact"}
        </button>
        {m.sector && (
          <a href={mapsUrl(m.sector)} target="_blank" rel="noopener"
            className="absolute left-2.5 bottom-2.5 text-xs font-semibold text-white bg-black/70 rounded-lg px-2.5 py-1 flex items-center gap-1.5 no-underline">
            📍 {m.sector} 🗺️
          </a>
        )}
      </div>
      <div className="p-4 flex flex-col flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-2xl font-black tracking-tight">{rupeesToCr(m.price) || "On request"}</span>
          {m.size_sqm && (
            <span className="text-xs font-bold rounded-full px-3 py-1 bg-[var(--color-brand-soft)] text-[var(--color-brand)]">
              {Math.round(m.size_sqm)} sqm
            </span>
          )}
        </div>
        <div className="text-sm font-semibold text-slate-700 mt-1 line-clamp-2 min-h-[2.5em]">
          {m.title ?? "Untitled listing"}
        </div>
        {m.description && (
          <p className="text-xs text-[var(--color-muted)] mt-1 line-clamp-2">{m.description}</p>
        )}
        <div className="mt-auto pt-3 flex items-center justify-between">
          <span className="text-xs text-[var(--color-muted)] font-semibold">
            {m.owner ? `Req · ${m.owner}` : `Req #${m.requirement_id}`}
          </span>
          {pct != null && (
            <span className={`text-xs font-extrabold rounded-full px-2.5 py-1 ${
              pct >= 80 ? "bg-green-100 text-green-700"
                : pct >= 60 ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-600"
            }`}>{pct}% match</span>
          )}
        </div>
        <div className="flex gap-2 mt-3">
          <button onClick={() => feedback.mutate("nope")}
            className={`flex-1 py-2 rounded-xl font-bold text-sm border ${
              m.verdict === "nope" ? "bg-red-500 text-white border-red-500" : "text-red-600 border-red-200 hover:bg-red-50"
            }`}>👎 Pass</button>
          <button onClick={() => feedback.mutate("like")}
            className={`flex-1 py-2 rounded-xl font-bold text-sm border ${
              m.verdict === "like" ? "bg-green-600 text-white border-green-600" : "text-green-600 border-green-200 hover:bg-green-50"
            }`}>👍 Like</button>
        </div>
      </div>
    </div>
  );
}
