# prop-search v2

Noida property finder, rebuilt as real software. **Producer → central store → consumer:**

- **`apps/scraper`** — Python CLI. Runs Chrome (Patchright) on a residential **India** box,
  scrapes MagicBricks, matches against requirements, pushes to Supabase. Timer-driven (6h).
- **Supabase** — hosted Postgres + Auth. Single source of truth (`supabase/migrations`).
- **`apps/api`** — FastAPI. Auth'd REST API between the UI and Supabase. Reuses the matcher.
- **`apps/web`** — Next.js + shadcn/ui. The UI; reachable from anywhere (e.g. Dubai).
- **`packages/core`** — shared Python: scrapers, matcher, property types, notifier.
- **`packages/types`** — TS API client generated from FastAPI's OpenAPI.

Full design + phased plan: **[docs/V2_PLAN.md](docs/V2_PLAN.md)**.

## Status

Phase 0 (foundations) — in progress. Schema + RLS migration ready under `supabase/`.
Subsequent phases (scraper → API → web → deploy → cutover) build in order; see the plan.

> The v1 Streamlit MVP still lives on the **`main`** branch and keeps running. v2 is
> developed on **`v2-overhaul`** (this worktree).

## Layout

```
apps/{web,api,scraper}   packages/{core,types}   supabase/migrations   docs/
```

## First-run (Phase 0)

See **[supabase/README.md](supabase/README.md)** to create the Supabase project and apply
the schema. Tooling: `pnpm` (web/types) + `uv` (api/scraper/core).
