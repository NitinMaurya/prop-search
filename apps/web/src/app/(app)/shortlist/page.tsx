"use client";

import { Suspense, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { rupeesToCr, mapsUrl, relativeTime } from "@/lib/format";
import { useUrlState } from "@/lib/useUrlState";
import { useMatchActions } from "@/lib/useMatchActions";
import { MatchCard } from "@/components/MatchCard";
import { Lightbox } from "@/components/Lightbox";
import { PageHeader } from "@/components/PageHeader";
import { Loading } from "@/components/Loading";
import type { Match } from "@/lib/types";

const TABS = [
  { key: "liked", label: "👍 Liked" },
  { key: "passed", label: "👎 Passed" },
  { key: "followups", label: "📞 Follow-ups" },
];

export default function ShortlistPage() {
  return (
    <Suspense fallback={<Loading />}>
      <ShortlistInner />
    </Suspense>
  );
}

function ShortlistInner() {
  const { get, set } = useUrlState();
  const tab = get("tab", "liked");
  const setTab = (k: string) => set({ tab: k === "liked" ? null : k });
  const showCode = tab === "passed" ? "passed" : tab === "liked" ? "liked" : "all";

  const { data: rows = [], isLoading } = useQuery({
    queryKey: ["matches", showCode, "shortlist"],
    queryFn: () => api.listMatches({ show: showCode, sort: "best" }),
  });

  const followups = rows.filter((m) => m.verdict === "like" || m.contacted_at);

  const imaged = rows.filter((m) => m.image_url);
  const idxOf = new Map(imaged.map((m, i) => [m.id, i] as const));
  const [lb, setLb] = useState<number | null>(null);

  return (
    <div>
      <PageHeader title="Shortlist" subtitle="Homes you reacted to — liked, passed, and your follow-up notes." />
      <div className="flex gap-2 mb-5">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-4 py-2 rounded-xl font-bold text-sm ${
              tab === t.key ? "ps-btn-grad" : "border border-[var(--color-line)] text-[var(--color-muted)]"
            }`}>{t.label}</button>
        ))}
      </div>

      {isLoading ? <Loading /> : tab === "followups" ? (
        followups.length === 0 ? (
          <Empty icon="📞" title="No follow-ups yet"
            sub="Like a listing or mark it Contacted — it shows up here to track." />
        ) : (
          <div className="flex flex-col gap-3 max-w-3xl">
            <p className="text-sm text-[var(--color-muted)]">
              {followups.filter((m) => m.contacted_at).length} contacted · {followups.length} tracked
            </p>
            {followups.map((m) => (
              <FollowupRow key={m.id} m={m}
                onZoom={idxOf.has(m.id) ? () => setLb(idxOf.get(m.id)!) : undefined} />
            ))}
          </div>
        )
      ) : (
        <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%,320px),1fr))" }}>
          {rows.length === 0 && <Empty icon={tab === "liked" ? "💚" : "🗂️"} title={`Nothing ${tab} yet`} />}
          {rows.map((m) => (
            <MatchCard key={m.match_id} m={m}
              onZoom={idxOf.has(m.id) ? () => setLb(idxOf.get(m.id)!) : undefined} />
          ))}
        </div>
      )}

      <Lightbox items={imaged} index={lb} onIndex={setLb} onClose={() => setLb(null)} />
    </div>
  );
}

function FollowupRow({ m, onZoom }: { m: Match; onZoom?: () => void }) {
  const qc = useQueryClient();
  const { contacted } = useMatchActions(m);
  const [notes, setNotes] = useState(m.notes ?? "");
  const [saved, setSaved] = useState(false);
  const saveNote = useMutation({
    mutationFn: () => api.setNote(m.id, notes),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["matches"] }); setSaved(true); },
  });
  const isContacted = !!m.contacted_at;
  const dirty = notes !== (m.notes ?? "");

  return (
    <div className={`ps-card p-4 flex gap-4 border-l-4 ${isContacted ? "border-l-blue-500" : "border-l-transparent"}`}>
      {/* thumbnail → lightbox */}
      <button type="button" onClick={onZoom} disabled={!onZoom}
        className={`shrink-0 w-24 h-20 rounded-xl overflow-hidden bg-[var(--color-brand-soft)] flex items-center justify-center ${onZoom ? "cursor-zoom-in" : ""}`}>
        {m.image_url
          ? // eslint-disable-next-line @next/next/no-img-element
            <img src={m.image_url} alt="" className="w-full h-full object-cover" />
          : <span className="text-2xl opacity-50">🏠</span>}
      </button>

      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <a href={m.url ?? "#"} target="_blank" rel="noopener" className="font-bold hover:underline block truncate">
              {m.title ?? "Untitled listing"}
            </a>
            <div className="text-xs text-[var(--color-muted)] mt-0.5 flex flex-wrap items-center gap-x-2.5 gap-y-1">
              {m.price ? <span className="font-semibold text-[var(--color-ink)]">{rupeesToCr(m.price)}</span> : null}
              {m.size_sqm ? <span>{Math.round(m.size_sqm)} sqm</span> : null}
              {m.sector && (
                <a href={mapsUrl(m.sector)} target="_blank" rel="noopener"
                  className="font-semibold text-[var(--color-brand-dk)] hover:underline">📍 {m.sector}</a>
              )}
            </div>
          </div>
          <div className="shrink-0 flex flex-col items-end gap-1.5">
            <button onClick={() => contacted.mutate()}
              className={`text-xs font-bold px-3 py-1.5 rounded-lg border ${
                isContacted ? "bg-blue-600 text-white border-blue-600" : "text-blue-600 border-blue-200 hover:bg-blue-50"}`}>
              {isContacted ? "✅ Contacted" : "📞 Mark contacted"}
            </button>
            {isContacted && (
              <span className="text-[11px] text-[var(--color-muted)]">{relativeTime(m.contacted_at)}</span>
            )}
          </div>
        </div>

        <div className="relative mt-2.5">
          <textarea value={notes} rows={2}
            onChange={(e) => { setNotes(e.target.value); setSaved(false); }}
            onBlur={() => dirty && saveNote.mutate()}
            placeholder="Notes — asking price, broker name, next step…"
            className="w-full rounded-xl border border-[var(--color-line)] p-2.5 pr-16 text-sm outline-none focus:border-[var(--color-brand)] resize-y" />
          <span className="absolute right-3 bottom-2.5 text-[11px] font-semibold">
            {saveNote.isPending ? <span className="text-[var(--color-muted)]">Saving…</span>
              : dirty ? <span className="text-amber-600">Unsaved</span>
              : saved ? <span className="text-green-600">✓ Saved</span> : null}
          </span>
        </div>
      </div>
    </div>
  );
}

function Empty({ icon, title, sub }: { icon: string; title: string; sub?: string }) {
  return (
    <div className="ps-card p-12 text-center col-span-full">
      <div className="text-5xl mb-2">{icon}</div>
      <div className="text-lg font-bold">{title}</div>
      {sub && <p className="text-[var(--color-muted)] mt-1">{sub}</p>}
    </div>
  );
}
