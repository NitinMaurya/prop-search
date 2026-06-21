"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { rupeesToCr, CR } from "@/lib/format";
import { PageHeader } from "@/components/PageHeader";
import type { Requirement, RequirementInput } from "@/lib/types";

const TYPES = [
  ["house", "Independent House / Kothi / Villa"],
  ["plot", "Plot / Land"],
  ["apartment", "Apartment / Flat"],
];

export default function RequirementsPage() {
  const qc = useQueryClient();
  const { data: reqs = [], isLoading } = useQuery({
    queryKey: ["requirements"], queryFn: api.listRequirements,
  });
  const [editing, setEditing] = useState<Requirement | "new" | null>(null);

  const del = useMutation({
    mutationFn: (id: number) => api.deleteRequirement(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["requirements"] }),
  });

  return (
    <div>
      <PageHeader title="Requirements" subtitle="Your saved property queries. The scraper checks every active one each run." />

      <div className="flex justify-between items-center mb-4">
        <span className="text-xs font-bold uppercase tracking-wide text-[var(--color-muted)]">
          {reqs.length} requirement{reqs.length !== 1 ? "s" : ""}
        </span>
        <button onClick={() => setEditing("new")} className="ps-btn-grad rounded-xl px-4 py-2 font-bold text-sm">
          ➕ New requirement
        </button>
      </div>

      {isLoading && <p className="text-[var(--color-muted)]">Loading…</p>}

      <div className="ps-card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b-2 border-[var(--color-line)] text-left">
              {["Owner", "Type", "Budget", "Sectors", "Status", ""].map((h) => (
                <th key={h} className="px-5 py-4 font-extrabold text-base">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {reqs.map((r) => (
              <tr key={r.id} className="border-b border-[var(--color-line)] last:border-0 hover:bg-slate-50">
                <td className="px-5 py-3 font-bold">{r.owner ?? "—"}</td>
                <td className="px-5 py-3 text-slate-600">{TYPES.find((t) => t[0] === r.property_type)?.[1] ?? r.property_type}</td>
                <td className="px-5 py-3">{rupeesToCr(r.budget_min)?.replace("₹ ", "₹") }–{rupeesToCr(r.budget_max)?.replace("₹ ", "")}</td>
                <td className="px-5 py-3 text-slate-600">📍 {r.sectors.length ? r.sectors.join(", ") : "all Noida"}</td>
                <td className="px-5 py-3">
                  <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${r.active ? "bg-green-100 text-green-700" : "bg-slate-100 text-slate-500"}`}>
                    ● {r.active ? "Active" : "Paused"}
                  </span>
                </td>
                <td className="px-5 py-3 text-right">
                  <button onClick={() => setEditing(r)} className="px-3 py-1.5 rounded-lg border border-[var(--color-line)] hover:bg-slate-100">✏️</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && (
        <RequirementDialog
          req={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onDelete={editing !== "new" ? () => { del.mutate((editing as Requirement).id); setEditing(null); } : undefined}
        />
      )}
    </div>
  );
}

function RequirementDialog({ req, onClose, onDelete }: {
  req: Requirement | null; onClose: () => void; onDelete?: () => void;
}) {
  const qc = useQueryClient();
  const [owner, setOwner] = useState(req?.owner ?? "");
  const [propertyType, setPropertyType] = useState(req?.property_type ?? "house");
  const [sizes, setSizes] = useState((req?.sizes_sqm ?? [112, 162]).join(", "));
  const [tol, setTol] = useState(req?.size_tolerance_pct ?? 30);
  const [bmin, setBmin] = useState(req ? (req.budget_min ?? 0) / CR : 4);
  const [bmax, setBmax] = useState(req ? (req.budget_max ?? 0) / CR : 5);
  const [sectors, setSectors] = useState((req?.sectors ?? []).join(", "));
  const [active, setActive] = useState(req?.active ?? true);
  const [confirmDel, setConfirmDel] = useState(false);

  const save = useMutation({
    mutationFn: () => {
      const body: RequirementInput = {
        owner: owner.trim() || null,
        property_type: propertyType,
        sizes_sqm: sizes.split(",").map((s) => parseInt(s.trim(), 10)).filter((n) => !isNaN(n)),
        size_tolerance_pct: Number(tol),
        budget_min: Math.round(bmin * CR),
        budget_max: Math.round(bmax * CR),
        sectors: sectors.split(",").map((s) => s.trim()).filter(Boolean),
        active,
      };
      return req ? api.updateRequirement(req.id, body) : api.createRequirement(body);
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["requirements"] }); onClose(); },
  });

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50" onClick={onClose}>
      <div className="ps-card w-full max-w-xl p-6" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-xl font-extrabold mb-4">{req ? "Edit requirement" : "New requirement"}</h2>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Owner"><input className="inp" value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="e.g. nitin" /></Field>
          <Field label="Property type">
            <select className="inp" value={propertyType} onChange={(e) => setPropertyType(e.target.value)}>
              {TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </Field>
          <Field label="Budget min (Cr)"><input type="number" step="0.1" className="inp" value={bmin} onChange={(e) => setBmin(+e.target.value)} /></Field>
          <Field label="Budget max (Cr)"><input type="number" step="0.1" className="inp" value={bmax} onChange={(e) => setBmax(+e.target.value)} /></Field>
          <Field label="Sizes (sqm, comma)"><input className="inp" value={sizes} onChange={(e) => setSizes(e.target.value)} /></Field>
          <Field label="Size tolerance (%)"><input type="number" className="inp" value={tol} onChange={(e) => setTol(+e.target.value)} /></Field>
        </div>
        <Field label="Sectors (comma; empty = all Noida)"><input className="inp" value={sectors} onChange={(e) => setSectors(e.target.value)} placeholder="e.g. 28, 50, 105" /></Field>
        <label className="flex items-center gap-2 mt-3 font-semibold text-sm">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Active — included in every scrape
        </label>

        <div className="flex gap-2 mt-5">
          <button onClick={() => save.mutate()} className="ps-btn-grad rounded-xl px-4 py-2.5 font-bold flex-1">💾 Save</button>
          <button onClick={onClose} className="rounded-xl px-4 py-2.5 font-bold border border-[var(--color-line)]">Cancel</button>
        </div>
        {onDelete && (
          <div className="mt-3 pt-3 border-t border-[var(--color-line)]">
            {confirmDel ? (
              <div className="flex items-center gap-2">
                <span className="text-sm text-[var(--color-muted)]">⚠️ Delete permanently?</span>
                <button onClick={onDelete} className="rounded-lg px-3 py-1.5 bg-red-500 text-white font-bold text-sm">Yes, delete</button>
                <button onClick={() => setConfirmDel(false)} className="rounded-lg px-3 py-1.5 border border-[var(--color-line)] text-sm">Cancel</button>
              </div>
            ) : (
              <button onClick={() => setConfirmDel(true)} className="text-sm font-semibold text-red-600">🗑 Delete requirement</button>
            )}
          </div>
        )}
      </div>
      <style jsx>{`
        .inp { width: 100%; border: 1px solid var(--color-line); border-radius: 11px; padding: 0.5rem 0.75rem; outline: none; }
        .inp:focus { border-color: var(--color-brand); }
      `}</style>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 mt-3">
      <span className="text-xs font-bold uppercase tracking-wide text-[var(--color-muted)]">{label}</span>
      {children}
    </label>
  );
}
