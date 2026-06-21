"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { mapsUrl, rupeesToCr } from "@/lib/format";
import type { Match, Verdict } from "@/lib/types";

export function MatchTable({ rows }: { rows: Match[] }) {
  return (
    <div className="ps-card overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b-2 border-[var(--color-line)] text-left">
            {["", "Listing", "Size", "Price", "Match", "Actions"].map((h) => (
              <th key={h} className="px-4 py-3 font-extrabold whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => <Row key={m.match_id} m={m} />)}
        </tbody>
      </table>
    </div>
  );
}

function Row({ m }: { m: Match }) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["matches"] });
  const feedback = useMutation({
    mutationFn: ({ v }: { v: Verdict }) => api.setFeedback(m.id, v),
    onSuccess: invalidate,
  });
  const contacted = useMutation({ mutationFn: () => api.setContacted(m.id), onSuccess: invalidate });
  const pct = m.score != null ? Math.round(m.score * 100) : null;

  return (
    <tr className={`border-b border-[var(--color-line)] last:border-0 hover:bg-slate-50 ${m.verdict === "nope" ? "opacity-60" : ""}`}>
      <td className="px-4 py-2.5">
        <div className="w-16 h-12 rounded-lg overflow-hidden bg-[var(--color-brand-soft)] flex items-center justify-center shrink-0">
          {m.image_url
            ? // eslint-disable-next-line @next/next/no-img-element
              <img src={m.image_url} alt="" className="w-full h-full object-cover" />
            : <span className="opacity-50">🏠</span>}
        </div>
      </td>
      <td className="px-4 py-2.5 max-w-[420px]">
        <a href={m.url ?? "#"} target="_blank" rel="noopener" className="font-bold hover:underline line-clamp-1">
          {m.title ?? "Untitled listing"}
          {m.is_new && <span className="ml-2 align-middle text-[10px] font-extrabold text-white bg-emerald-500 rounded px-1.5 py-0.5">NEW</span>}
        </a>
        <div className="text-xs text-[var(--color-muted)] mt-0.5">
          {m.sector && (
            <a href={mapsUrl(m.sector)} target="_blank" rel="noopener" className="font-semibold text-[var(--color-brand-dk)] hover:underline">
              📍 {m.sector} 🗺️
            </a>
          )}
          {m.advertiser ? ` · ${m.advertiser}` : ""}
        </div>
      </td>
      <td className="px-4 py-2.5 whitespace-nowrap">{m.size_sqm ? `${Math.round(m.size_sqm)} sqm` : "—"}</td>
      <td className="px-4 py-2.5 whitespace-nowrap font-semibold">{rupeesToCr(m.price) || "—"}</td>
      <td className="px-4 py-2.5">
        {pct != null && (
          <span className={`text-xs font-extrabold rounded-full px-2 py-1 ${
            pct >= 80 ? "bg-green-100 text-green-700" : pct >= 60 ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-600"
          }`}>{pct}%</span>
        )}
      </td>
      <td className="px-4 py-2.5">
        <div className="flex gap-1.5 whitespace-nowrap">
          <button onClick={() => feedback.mutate({ v: "nope" })}
            className={`px-2.5 py-1 rounded-lg text-xs font-bold border ${m.verdict === "nope" ? "bg-red-500 text-white border-red-500" : "text-red-600 border-red-200 hover:bg-red-50"}`}>👎</button>
          <button onClick={() => feedback.mutate({ v: "like" })}
            className={`px-2.5 py-1 rounded-lg text-xs font-bold border ${m.verdict === "like" ? "bg-green-600 text-white border-green-600" : "text-green-600 border-green-200 hover:bg-green-50"}`}>👍</button>
          <button onClick={() => contacted.mutate()}
            className={`px-2.5 py-1 rounded-lg text-xs font-bold border ${m.contacted_at ? "bg-blue-600 text-white border-blue-600" : "text-blue-600 border-blue-200 hover:bg-blue-50"}`}>📞</button>
        </div>
      </td>
    </tr>
  );
}
