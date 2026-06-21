export function Spinner({ size = 24 }: { size?: number }) {
  return (
    <div
      className="animate-spin rounded-full border-2 border-[var(--color-line)] border-t-[var(--color-brand)]"
      style={{ width: size, height: size }}
      role="status" aria-label="Loading"
    />
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-24 text-[var(--color-muted)]">
      <Spinner size={30} />
      <span className="text-sm font-semibold">{label}</span>
    </div>
  );
}

/** Pulsing placeholders shaped like the match cards, for the Matches grid. */
export function SkeletonCards({ n = 8 }: { n?: number }) {
  return (
    <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%,320px),1fr))" }}>
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="ps-card overflow-hidden">
          <div className="aspect-[16/10] bg-slate-200 animate-pulse" />
          <div className="p-4 space-y-3">
            <div className="h-6 w-1/2 rounded bg-slate-200 animate-pulse" />
            <div className="h-4 w-full rounded bg-slate-200 animate-pulse" />
            <div className="h-4 w-2/3 rounded bg-slate-200 animate-pulse" />
            <div className="flex gap-2 pt-2">
              <div className="h-8 flex-1 rounded-xl bg-slate-200 animate-pulse" />
              <div className="h-8 flex-1 rounded-xl bg-slate-200 animate-pulse" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

/** Pulsing placeholder rows for table/list pages. */
export function SkeletonRows({ n = 6 }: { n?: number }) {
  return (
    <div className="ps-card divide-y divide-[var(--color-line)]">
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 p-4">
          <div className="h-10 w-16 rounded-lg bg-slate-200 animate-pulse" />
          <div className="flex-1 space-y-2">
            <div className="h-4 w-1/3 rounded bg-slate-200 animate-pulse" />
            <div className="h-3 w-1/4 rounded bg-slate-200 animate-pulse" />
          </div>
        </div>
      ))}
    </div>
  );
}
