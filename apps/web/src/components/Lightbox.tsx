"use client";

import { useEffect } from "react";
import { rupeesToCr } from "@/lib/format";
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

  if (index === null || !items[index]) return null;
  const m = items[index];

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

      {/* fixed bottom banner: title as a heading + meta + open-listing */}
      <div onClick={(e) => e.stopPropagation()}
        className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 via-black/75 to-transparent
                   px-5 sm:px-10 pt-10 pb-6 flex items-end justify-between gap-5">
        <div className="min-w-0">
          <h2 className="text-white text-xl sm:text-2xl font-extrabold tracking-tight leading-tight truncate">
            {m.title ?? "Untitled listing"}
          </h2>
          <div className="mt-1 text-sm font-semibold text-white/75 flex flex-wrap items-center gap-x-3 gap-y-1">
            {m.price ? <span className="text-white">{rupeesToCr(m.price)}</span> : null}
            {m.size_sqm ? <span>{Math.round(m.size_sqm)} sqm</span> : null}
            {m.sector ? <span>📍 {m.sector}</span> : null}
            <span className="text-white/50">{index + 1} / {items.length}</span>
          </div>
        </div>
        {m.url && (
          <a href={m.url} target="_blank" rel="noopener"
            className="ps-btn-grad rounded-xl px-5 py-2.5 font-bold shrink-0 no-underline whitespace-nowrap">
            Open listing ↗
          </a>
        )}
      </div>
    </div>
  );
}
