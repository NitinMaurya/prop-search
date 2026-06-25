"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { Match } from "./types";

/**
 * Click-to-contact via the user's OWN logged-in MagicBricks session (option B).
 *
 * Cross-origin JS can't click buttons on magicbricks.com, so we open the listing in a new
 * tab carrying a `?psac=<id>.<nonce>` flag; the prop-search userscript (tools/…user.js)
 * runs ON that page, clicks "Contact Owner", and postMessage()s the real outcome back here.
 * We mark `contacted_at` only on a confirmed success — never just because the tab opened.
 *
 * "pending" lives here in memory (it's the time the user's other tab is working); the only
 * persisted truth is the server's `contacted_at`. No job queue, no server worker.
 */

export type ContactState = "idle" | "pending" | "failed" | "done";

/** Shared label + behaviour per state so the card, table and lightbox buttons match. */
export const CONTACT_BTN: Record<ContactState, { label: string; canStart: boolean; disabled: boolean }> = {
  idle: { label: "📞 Contact", canStart: true, disabled: false },
  pending: { label: "⏳ Contacting…", canStart: false, disabled: true },
  failed: { label: "⚠️ Retry", canStart: true, disabled: false },
  done: { label: "✅ Contacted", canStart: false, disabled: true },
};

const MB_ORIGIN = "https://www.magicbricks.com";
const REPLY_TIMEOUT_MS = 90_000; // give the user's tab time to load + click

type Pending = { nonce: string; timer: ReturnType<typeof setTimeout> };

interface ContactCtx {
  start: (m: Match) => void;
  /** state for a listing, given its server contacted_at (which wins once set). */
  stateOf: (listingId: number, contactedAt?: string | null) => ContactState;
}

const Ctx = createContext<ContactCtx | null>(null);

export function ContactProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();
  const pending = useRef(new Map<number, Pending>());
  const [, force] = useState(0);
  const [failed, setFailed] = useState<Set<number>>(new Set());
  const [hint, setHint] = useState<string | null>(null);

  const rerender = () => force((n) => n + 1);

  const clear = useCallback((listingId: number) => {
    const p = pending.current.get(listingId);
    if (p) clearTimeout(p.timer);
    pending.current.delete(listingId);
    rerender();
  }, []);

  const start = useCallback((m: Match) => {
    if (!m.url) { setHint("This listing has no MagicBricks URL."); return; }
    const nonce = crypto.randomUUID().slice(0, 8);
    const sep = m.url.includes("?") ? "&" : "?";
    const w = window.open(`${m.url}${sep}psac=${m.id}.${nonce}`, "_blank");
    if (!w) { setHint("Popup blocked — allow popups for prop-search, then click Contact again."); return; }
    setFailed((s) => { const n = new Set(s); n.delete(m.id); return n; });
    const timer = setTimeout(() => {
      pending.current.delete(m.id);
      setHint("Couldn't confirm the contact. Install the MagicBricks auto-contact userscript, " +
              "or click “Contact Owner” in the tab that opened.");
      rerender();
    }, REPLY_TIMEOUT_MS);
    pending.current.set(m.id, { nonce, timer });
    rerender();
  }, []);

  // One global listener for the userscript's reply.
  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (e.origin !== MB_ORIGIN) return;
      const d = e.data;
      if (!d || d.source !== "ps-autocontact") return;
      const listingId = Number(d.listingId);
      const p = pending.current.get(listingId);
      if (!p || p.nonce !== d.nonce) return; // stale / not ours
      clear(listingId);
      if (d.ok) {
        api.setContacted(listingId, true)
          .then(() => qc.invalidateQueries({ queryKey: ["matches"] }))
          .catch(() => setHint("Contacted on MagicBricks, but failed to save it here."));
      } else {
        setFailed((s) => new Set(s).add(listingId));
        setHint(`MagicBricks couldn't complete the contact${d.error ? `: ${d.error}` : "."}`);
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [clear, qc]);

  const stateOf = useCallback((listingId: number, contactedAt?: string | null): ContactState => {
    if (contactedAt) return "done";
    if (pending.current.has(listingId)) return "pending";
    if (failed.has(listingId)) return "failed";
    return "idle";
  }, [failed]);

  return (
    <Ctx.Provider value={{ start, stateOf }}>
      {children}
      {hint && (
        <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-[120] max-w-md">
          <div className="ps-card bg-[var(--color-ink)] text-white px-4 py-3 text-sm font-semibold flex items-start gap-3 shadow-xl">
            <span className="flex-1">{hint}</span>
            <button onClick={() => setHint(null)} className="text-white/70 hover:text-white">✕</button>
          </div>
        </div>
      )}
    </Ctx.Provider>
  );
}

export function useContact(): ContactCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useContact must be used within <ContactProvider>");
  return ctx;
}
