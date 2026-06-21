"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { rupeesToCr } from "@/lib/format";
import { MatchCard } from "@/components/MatchCard";
import { PageHeader } from "@/components/PageHeader";
import type { Match } from "@/lib/types";

const TABS = [
  { key: "liked", label: "👍 Liked" },
  { key: "passed", label: "👎 Passed" },
  { key: "followups", label: "📞 Follow-ups" },
];

export default function ShortlistPage() {
  const [tab, setTab] = useState("liked");
  const showCode = tab === "passed" ? "passed" : tab === "liked" ? "liked" : "all";

  const { data: rows = [] } = useQuery({
    queryKey: ["matches", showCode, "shortlist"],
    queryFn: () => api.listMatches({ show: showCode, sort: "best" }),
  });

  const followups = rows.filter((m) => m.verdict === "like" || m.contacted_at);

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

      {tab === "followups" ? (
        <div className="flex flex-col gap-3">
          {followups.length === 0 && <Empty icon="📞" title="No follow-ups yet" />}
          {followups.map((m) => <FollowupRow key={m.id} m={m} />)}
        </div>
      ) : (
        <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%,290px),1fr))" }}>
          {rows.length === 0 && <Empty icon={tab === "liked" ? "💚" : "🗂️"} title={`Nothing ${tab} yet`} />}
          {rows.map((m) => <MatchCard key={m.match_id} m={m} />)}
        </div>
      )}
    </div>
  );
}

function FollowupRow({ m }: { m: Match }) {
  const qc = useQueryClient();
  const [notes, setNotes] = useState(m.notes ?? "");
  const saveNote = useMutation({
    mutationFn: () => api.setNote(m.id, notes),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["matches"] }),
  });
  const contacted = useMutation({
    mutationFn: () => api.setContacted(m.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["matches"] }),
  });

  return (
    <div className="ps-card p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <a href={m.url ?? "#"} target="_blank" rel="noopener" className="font-bold hover:underline">
            {m.title ?? "Untitled listing"}
          </a>
          <div className="text-xs text-[var(--color-muted)] mt-0.5">
            {rupeesToCr(m.price)} {m.sector ? `· 📍 ${m.sector}` : ""}
            {m.contacted_at ? ` · ✅ contacted` : ""}
          </div>
        </div>
        <button onClick={() => contacted.mutate()}
          className="shrink-0 text-xs font-bold px-3 py-1.5 rounded-lg border border-blue-200 text-blue-600 hover:bg-blue-50">
          {m.contacted_at ? "↩︎ Undo" : "📞 Contacted"}
        </button>
      </div>
      <textarea value={notes} onChange={(e) => setNotes(e.target.value)} onBlur={() => saveNote.mutate()}
        placeholder="Follow-up notes — asking price, broker, next step…"
        className="w-full mt-3 rounded-xl border border-[var(--color-line)] p-2.5 text-sm outline-none focus:border-[var(--color-brand)]" rows={2} />
    </div>
  );
}

function Empty({ icon, title }: { icon: string; title: string }) {
  return (
    <div className="ps-card p-12 text-center col-span-full">
      <div className="text-5xl mb-2">{icon}</div>
      <div className="text-lg font-bold">{title}</div>
    </div>
  );
}
