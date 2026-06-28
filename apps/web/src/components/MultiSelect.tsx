"use client";

import { useEffect, useRef, useState } from "react";

/** A dropdown that toggles multiple options via checkboxes (the app's Select is single-
 * choice). Closes on outside-click / Escape. Styled to match Select. */
export function MultiSelect({ label, placeholder = "Any", options, selected, onToggle }: {
  label: string;
  placeholder?: string;
  options: { value: string; label: string; count?: number }[];
  selected: Set<string>;
  onToggle: (value: string, on: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const count = options.reduce((n, o) => n + (selected.has(o.value) ? 1 : 0), 0);

  return (
    <div ref={ref} className="relative flex flex-col gap-1">
      <span className="text-xs font-bold uppercase tracking-wide text-[var(--color-muted)]">{label}</span>
      <button type="button" onClick={() => setOpen((o) => !o)}
        className="min-w-[150px] flex items-center justify-between gap-2 rounded-xl border border-[var(--color-line)] bg-white px-3 py-2 text-sm font-semibold outline-none focus:border-[var(--color-brand)]">
        <span className={count ? "text-[var(--color-ink)]" : "text-[var(--color-muted)]"}>
          {count === 0 ? placeholder : `${count} selected`}
        </span>
        <span className="text-[var(--color-muted)] text-xs">▾</span>
      </button>
      {open && (
        <div className="absolute top-full left-0 z-30 mt-1 w-max min-w-full max-h-72 overflow-auto rounded-xl border border-[var(--color-line)] bg-white p-1 shadow-lg">
          {options.map((o) => (
            <label key={o.value}
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold cursor-pointer hover:bg-[var(--color-brand-soft)] whitespace-nowrap">
              <input type="checkbox" checked={selected.has(o.value)}
                onChange={(e) => onToggle(o.value, e.target.checked)} />
              {o.label}{o.count != null ? ` (${o.count})` : ""}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
