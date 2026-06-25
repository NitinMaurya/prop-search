"use client";

import { mapsUrl, rupeesToCr, sectorLabel } from "@/lib/format";
import { useMatchActions } from "@/lib/useMatchActions";
import { CONTACT_BTN, useContact } from "@/lib/useContact";
import type { Match } from "@/lib/types";

export function MatchTable({ rows, onZoom }: {
  rows: Match[];
  onZoom?: (listingId: number) => void;
}) {
  return (
    <div className="ps-card overflow-x-auto">
      <table className="w-full text-sm table-fixed min-w-[760px]">
        <colgroup>
          <col style={{ width: "84px" }} />
          <col />
          <col style={{ width: "92px" }} />
          <col style={{ width: "120px" }} />
          <col style={{ width: "76px" }} />
          <col style={{ width: "168px" }} />
        </colgroup>
        <thead>
          <tr className="border-b-2 border-[var(--color-line)] text-left">
            <th className="px-4 py-3" />
            <th className="px-4 py-3 font-extrabold">Listing</th>
            <th className="px-4 py-3 font-extrabold">Size</th>
            <th className="px-4 py-3 font-extrabold">Price</th>
            <th className="px-4 py-3 font-extrabold">Match</th>
            <th className="px-4 py-3 font-extrabold text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => <Row key={m.match_id} m={m} onZoom={onZoom} />)}
        </tbody>
      </table>
    </div>
  );
}

function Row({ m, onZoom }: { m: Match; onZoom?: (id: number) => void }) {
  const { feedback } = useMatchActions(m);
  const contact = useContact();
  const cState = contact.stateOf(m.id, m.contacted_at);
  const pct = m.score != null ? Math.round(m.score * 100) : null;
  const canZoom = !!(m.image_url && onZoom);

  return (
    <tr className={`border-b border-[var(--color-line)] last:border-0 hover:bg-slate-50 ${m.verdict === "nope" ? "opacity-60" : ""}`}>
      <td className="px-4 py-2.5">
        <button type="button" onClick={() => canZoom && onZoom!(m.id)} disabled={!canZoom}
          className={`w-[52px] h-[40px] rounded-lg overflow-hidden bg-[var(--color-brand-soft)] flex items-center justify-center ${canZoom ? "cursor-zoom-in" : ""}`}>
          {m.image_url
            ? // eslint-disable-next-line @next/next/no-img-element
              <img src={m.image_url} alt="" className="w-full h-full object-cover" />
            : <span className="opacity-50">🏠</span>}
        </button>
      </td>

      <td className="px-4 py-2.5 overflow-hidden">
        <a href={m.url ?? "#"} target="_blank" rel="noopener"
          className="font-bold hover:underline block truncate">
          {m.title ?? "Untitled listing"}
          {m.is_new && <span className="ml-2 align-middle text-[10px] font-extrabold text-white bg-emerald-500 rounded px-1.5 py-0.5">NEW</span>}
        </a>
        <div className="text-xs text-[var(--color-muted)] mt-0.5 truncate">
          {m.sector && (
            <a href={mapsUrl(m.sector)} target="_blank" rel="noopener"
              className="font-semibold text-[var(--color-brand-dk)] hover:underline">📍 {sectorLabel(m.sector)}</a>
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
        <div className="flex gap-1.5 justify-end">
          <button onClick={() => feedback.mutate({ v: "nope" })}
            className={`px-2.5 py-1 rounded-lg text-xs font-bold border ${m.verdict === "nope" ? "bg-red-500 text-white border-red-500" : "text-red-600 border-red-200 hover:bg-red-50"}`}>👎</button>
          <button onClick={() => feedback.mutate({ v: "like" })}
            className={`px-2.5 py-1 rounded-lg text-xs font-bold border ${m.verdict === "like" ? "bg-green-600 text-white border-green-600" : "text-green-600 border-green-200 hover:bg-green-50"}`}>👍</button>
          <button
            onClick={() => { if (CONTACT_BTN[cState].canStart) contact.start(m); }}
            disabled={CONTACT_BTN[cState].disabled}
            title={CONTACT_BTN[cState].label}
            className={`px-2.5 py-1 rounded-lg text-xs font-bold border ${
              cState === "done" ? "bg-blue-600 text-white border-blue-600"
                : cState === "pending" ? "text-slate-400 border-slate-200 cursor-wait"
                : cState === "failed" ? "text-amber-700 border-amber-300 hover:bg-amber-50"
                : "text-blue-600 border-blue-200 hover:bg-blue-50"
            }`}>{cState === "done" ? "✅" : cState === "pending" ? "⏳" : cState === "failed" ? "⚠️" : "📞"}</button>
        </div>
      </td>
    </tr>
  );
}
