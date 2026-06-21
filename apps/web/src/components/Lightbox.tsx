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
        <div className="mt-3 flex items-center justify-between gap-4 text-white">
          <div className="min-w-0">
            <div className="font-bold truncate">{m.title ?? "Untitled listing"}</div>
            <div className="text-sm text-white/70">
              {rupeesToCr(m.price)}{m.sector ? ` · 📍 ${m.sector}` : ""} · {index + 1} / {items.length}
            </div>
          </div>
          {m.url && (
            <a href={m.url} target="_blank" rel="noopener"
              className="ps-btn-grad rounded-xl px-4 py-2 font-bold shrink-0 no-underline">
              Open listing ↗
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
