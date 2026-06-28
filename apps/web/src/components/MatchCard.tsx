"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { mapsUrl, rupeesToCr, sectorLabel } from "@/lib/format";
import { PASS_REASONS, useMatchActions } from "@/lib/useMatchActions";
import { CONTACT_BTN, useContact } from "@/lib/useContact";
import { FeatureChipsRow } from "@/components/FeatureChips";
import type { Match } from "@/lib/types";

export function MatchCard({ m, onZoom, enableNotes }: {
  m: Match;
  onZoom?: () => void;
  enableNotes?: boolean;   // Follow-ups: show notes in the description + an edit button
}) {
  const { feedback } = useMatchActions(m);
  const contact = useContact();
  const cState = contact.stateOf(m.id, m.contacted_at);
  const cBtn = CONTACT_BTN[cState];
  const pct = m.score != null ? Math.round(m.score * 100) : null;
  const [notesOpen, setNotesOpen] = useState(false);
  const [descOpen, setDescOpen] = useState(false);

  return (
    <div className={`ps-card relative overflow-hidden flex flex-col h-full ${m.verdict === "nope" ? "opacity-60 hover:opacity-100" : ""}`}>
      {m.url && (
        <a href={m.url} target="_blank" rel="noopener" aria-label="Open listing"
          className="absolute inset-0 z-[1]" />
      )}
      {/* photo — FIXED height so image size can never change the card; click to zoom */}
      <div className="relative z-[2] shrink-0 h-[200px] bg-[var(--color-brand-soft)]">
        {m.image_url
          ? // eslint-disable-next-line @next/next/no-img-element
            <img src={m.image_url} alt="" onClick={onZoom}
              className={`w-full h-full object-cover block ${onZoom ? "cursor-zoom-in" : ""}`} />
          : <button type="button" onClick={onZoom} disabled={!onZoom}
              title={onZoom ? "View full details" : undefined}
              className={`w-full h-full flex items-center justify-center text-4xl opacity-50 ${onZoom ? "cursor-pointer hover:opacity-70" : ""}`}>🏠</button>}
        {m.is_new && (
          <span className="absolute top-2.5 left-2.5 text-xs font-extrabold text-white px-2.5 py-1 rounded-full"
            style={{ background: "linear-gradient(135deg,#10b981,#059669)" }}>🆕 New</span>
        )}
        <button
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); if (cBtn.canStart) contact.start(m); }}
          disabled={cBtn.disabled}
          className={`absolute top-2.5 right-2.5 text-xs font-bold px-2.5 py-1.5 rounded-full border ${
            cState === "done" ? "bg-blue-600 text-white border-blue-600"
              : cState === "pending" ? "bg-white/90 text-slate-500 border-white/70 cursor-wait"
              : cState === "failed" ? "bg-amber-50 text-amber-700 border-amber-300"
              : "bg-white/90 text-blue-600 border-white/70"
          }`}>
          {cBtn.label}
        </button>
        {m.sector && (
          <a href={mapsUrl(m.sector)} target="_blank" rel="noopener"
            className="absolute left-2.5 bottom-2.5 text-xs font-semibold text-white bg-black/70 rounded-lg px-2.5 py-1 no-underline hover:bg-blue-600/90">
            📍 {sectorLabel(m.sector)}
          </a>
        )}
      </div>

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

        {/* description — or the user's notes when in Follow-ups mode */}
        <p className={`text-xs mt-1 ${descOpen ? "whitespace-pre-line" : "line-clamp-2"} min-h-[2.4em] ${
          enableNotes && !m.notes ? "italic text-[var(--color-muted)]/70" : "text-[var(--color-muted)]"}`}>
          {enableNotes ? (m.notes || "No notes yet — add some 📝") : (m.description ?? "")}
        </p>
        {/* View more / less — only for long descriptions (not in notes mode). Sits above
            the card's stretched link so the click expands instead of opening the listing. */}
        {!enableNotes && (m.description?.length ?? 0) > 120 && (
          <button
            onClick={(e) => { e.preventDefault(); e.stopPropagation(); setDescOpen((o) => !o); }}
            className="relative z-[2] self-start text-xs font-bold text-[var(--color-brand-dk)] hover:underline mt-0.5">
            {descOpen ? "Show less" : "View more"}
          </button>
        )}

        {/* derived facing / park-facing labels parsed from the description */}
        <FeatureChipsRow m={m} className="mt-2" />

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

        {enableNotes && (
          <button
            onClick={(e) => { e.preventDefault(); e.stopPropagation(); setNotesOpen(true); }}
            className="relative z-[2] mt-2 py-2 rounded-xl font-bold text-sm border border-[var(--color-line)] text-[var(--color-brand-dk)] hover:bg-[var(--color-brand-soft)]">
            {m.notes ? "📝 Edit notes" : "📝 Add notes"}
          </button>
        )}

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

      {notesOpen && <NotesModal m={m} onClose={() => setNotesOpen(false)} />}
    </div>
  );
}

function NotesModal({ m, onClose }: { m: Match; onClose: () => void }) {
  const qc = useQueryClient();
  const [text, setText] = useState(m.notes ?? "");
  const save = useMutation({
    mutationFn: () => api.setNote(m.id, text),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["matches"] }); onClose(); },
  });
  return (
    <div className="fixed inset-0 z-[90] bg-black/40 flex items-center justify-center p-4" onClick={onClose}>
      <div className="ps-card w-full max-w-md p-5" onClick={(e) => e.stopPropagation()}>
        <h3 className="font-extrabold text-lg">📝 Notes</h3>
        <p className="text-xs text-[var(--color-muted)] mb-3 truncate">{m.title ?? "Listing"}</p>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={5} autoFocus
          placeholder="Asking price, broker name, next step…"
          className="w-full rounded-xl border border-[var(--color-line)] p-3 text-sm outline-none focus:border-[var(--color-brand)] resize-y" />
        <div className="flex gap-2 mt-3">
          <button onClick={() => save.mutate()} disabled={save.isPending}
            className="ps-btn-grad rounded-xl px-4 py-2 font-bold flex-1 disabled:opacity-60">
            {save.isPending ? "Saving…" : "Save notes"}
          </button>
          <button onClick={onClose} className="rounded-xl px-4 py-2 font-bold border border-[var(--color-line)]">Cancel</button>
        </div>
      </div>
    </div>
  );
}
