"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";

export default function SettingsPage() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  const [form, setForm] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);

  useEffect(() => { if (data) setForm(data); }, [data]);

  const save = useMutation({
    mutationFn: () => api.updateSettings(form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["settings"] }); setSaved(true); },
  });

  const set = (k: string, v: string) => { setForm((f) => ({ ...f, [k]: v })); setSaved(false); };
  const num = (k: string) => form[k] ?? "";

  return (
    <div className="max-w-2xl">
      <PageHeader title="Settings" subtitle="How listings are scored and matched. Changes apply on the next scrape." />

      <div className="ps-card p-6 space-y-5">
        <Row label="Match threshold" hint="Minimum score (0–1) for a listing to surface">
          <input type="number" step="0.05" min="0" max="1" className="inp" value={num("threshold")} onChange={(e) => set("threshold", e.target.value)} />
        </Row>
        <div className="grid grid-cols-3 gap-3">
          <Row label="Weight: size"><input type="number" step="0.05" className="inp" value={num("w_size")} onChange={(e) => set("w_size", e.target.value)} /></Row>
          <Row label="Weight: price"><input type="number" step="0.05" className="inp" value={num("w_price")} onChange={(e) => set("w_price", e.target.value)} /></Row>
          <Row label="Weight: sector"><input type="number" step="0.05" className="inp" value={num("w_sector")} onChange={(e) => set("w_sector", e.target.value)} /></Row>
        </div>
        <Row label="Default size tolerance (%)"><input type="number" className="inp" value={num("size_tolerance_pct")} onChange={(e) => set("size_tolerance_pct", e.target.value)} /></Row>
        <Row label="NOIDA-authority only" hint="1 = only NOIDA-authority, non-freehold listings">
          <input type="number" min="0" max="1" className="inp" value={num("noida_authority_only")} onChange={(e) => set("noida_authority_only", e.target.value)} />
        </Row>
        <Row label="Stale threshold (runs)" hint="Mark a listing stale after this many missed runs">
          <input type="number" className="inp" value={num("stale_threshold")} onChange={(e) => set("stale_threshold", e.target.value)} />
        </Row>

        <div className="flex items-center gap-3 pt-2">
          <button onClick={() => save.mutate()} className="ps-btn-grad rounded-xl px-5 py-2.5 font-bold">Save settings</button>
          {saved && <span className="text-sm text-green-600 font-semibold">✓ Saved</span>}
        </div>
      </div>
      <style jsx>{`
        .inp { width: 100%; border: 1px solid var(--color-line); border-radius: 11px; padding: 0.5rem 0.75rem; outline: none; }
        .inp:focus { border-color: var(--color-brand); }
      `}</style>
    </div>
  );
}

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-sm font-bold">{label}</span>
      {hint && <span className="block text-xs text-[var(--color-muted)] mb-1">{hint}</span>}
      <div className="mt-1">{children}</div>
    </label>
  );
}
