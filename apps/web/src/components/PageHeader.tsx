export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-4">
      <h1 className="text-3xl font-extrabold tracking-tight text-[var(--color-ink)]">{title}</h1>
      {subtitle && <p className="text-[var(--color-muted)] mt-1 max-w-[62ch]">{subtitle}</p>}
    </div>
  );
}
