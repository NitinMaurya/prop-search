"use client";

import { useEffect } from "react";
import { rupeesToCr } from "@/lib/format";
import { PASS_REASONS, useMatchActions } from "@/lib/useMatchActions";
import type { Match } from "@/lib/types";

/** Fullscreen image gallery over the listings that have a photo. Prev/next + Esc/arrows. */
export function Lightbox({ items, index, onIndex, onClose }: {
  items: Match[];
  index: number | null;
  onIndex: (i: number) => void;
  onClose: () => void;
}) {
  useEffect(() => {
    if (index === null) return;
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowLeft" && index > 0) onIndex(index - 1);
      else if (e.key === "ArrowRight" && index < items.length - 1) onIndex(index + 1);
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [index, items.length, onIndex, onClose]);

  const m = index !== null ? items[index] : undefined;
  const { feedback, contacted } = useMatchActions(m);

  if (!m || index === null) return null;
  const pct = m.score != null ? Math.round(m.score * 100) : null;

  return (
    <div className="fixed inset-0 z-[100] bg-black/85 flex items-center justify-center p-4 sm:p-8"
      onClick={onClose}>
      <button onClick={onClose} aria-label="Close"
        className="absolute top-4 right-5 text-white/80 hover:text-white text-3xl leading-none">✕</button>
      {index > 0 && (
        <button onClick={(e) => { e.stopPropagation(); onIndex(index - 1); }} aria-label="Previous"
          className="absolute left-3 sm:left-6 text-white/70 hover:text-white text-5xl leading-none">‹</button>
      )}
      {index < items.length - 1 && (
        <button onClick={(e) => { e.stopPropagation(); onIndex(index + 1); }} aria-label="Next"
          className="absolute right-3 sm:right-6 text-white/70 hover:text-white text-5xl leading-none">›</button>
      )}
      <div className="max-w-4xl w-full" onClick={(e) => e.stopPropagation()}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={m.image_url!} alt="" className="w-full max-h-[78vh] object-contain rounded-xl bg-black" />
      </div>

      {/* fixed bottom banner: heading + full details + open-listing */}
      <div onClick={(e) => e.stopPropagation()}
        className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black via-black/85 to-transparent
                   px-5 sm:px-12 pt-16 pb-8 flex items-end justify-between gap-6">
        <div className="min-w-0 max-w-3xl">
          <h2 className="text-white text-2xl sm:text-3xl font-extrabold tracking-tight leading-tight">
            {m.title ?? "Untitled listing"}
          </h2>

          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5 font-semibold">
            {m.price ? <span className="text-white text-lg">{rupeesToCr(m.price)}</span> : null}
            {m.size_sqm ? <span className="text-white/75">{Math.round(m.size_sqm)} sqm</span> : null}
            {m.sector ? <span className="text-white/75">📍 {m.sector}</span> : null}
            {pct != null && (
              <span className="text-xs font-extrabold rounded-full px-2.5 py-1 bg-white/15 text-white">
                {pct}% match
              </span>
            )}
            <span className="text-white/45 text-sm">{index + 1} / {items.length}</span>
          </div>

          {(m.advertiser || m.ownership || m.approving_authority) && (
            <div className="mt-2 flex flex-wrap gap-2">
              {[m.advertiser, m.ownership, m.approving_authority].filter(Boolean).map((chip, i) => (
                <span key={i} className="text-xs font-semibold rounded-md px-2 py-1 bg-white/10 text-white/80">
                  {chip}
                </span>
              ))}
            </div>
          )}

          {/* same actions as the cards: like / pass (+ reasons) / contacted */}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button onClick={() => feedback.mutate({ v: "nope" })}
              className={`px-4 py-1.5 rounded-lg text-sm font-bold border ${
                m.verdict === "nope" ? "bg-red-500 text-white border-red-500"
                  : "text-white border-white/30 hover:bg-white/10"}`}>👎 Pass</button>
            <button onClick={() => feedback.mutate({ v: "like" })}
              className={`px-4 py-1.5 rounded-lg text-sm font-bold border ${
                m.verdict === "like" ? "bg-green-600 text-white border-green-600"
                  : "text-white border-white/30 hover:bg-white/10"}`}>👍 Like</button>
            <button onClick={() => contacted.mutate()}
              className={`px-4 py-1.5 rounded-lg text-sm font-bold border ${
                m.contacted_at ? "bg-blue-600 text-white border-blue-600"
                  : "text-white border-white/30 hover:bg-white/10"}`}>
              {m.contacted_at ? "✅ Contacted" : "📞 Contact"}{m.notes ? " 📝" : ""}
            </button>
          </div>
          {m.verdict === "nope" && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {PASS_REASONS.map(([code, label]) => (
                <button key={code} onClick={() => feedback.mutate({ v: "nope", reason: code })}
                  className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${
                    m.pass_reason === code ? "bg-red-500 text-white border-red-500"
                      : "text-white/80 border-white/25 hover:bg-white/10"}`}>{label}</button>
              ))}
            </div>
          )}

          {m.description && (
            <p className="mt-3 text-sm leading-relaxed text-white/80 max-h-[24vh] overflow-y-auto pr-2">
              {m.description}
            </p>
          )}
        </div>

        {m.url && (
          <a href={m.url} target="_blank" rel="noopener"
            className="ps-btn-grad rounded-xl px-6 py-3 font-bold shrink-0 no-underline whitespace-nowrap">
            Open listing ↗
          </a>
        )}
      </div>
    </div>
  );
}
