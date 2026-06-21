# prop-search v2 — production overhaul plan

Status: **planning**. This supersedes the Streamlit MVP (`app.py`) once Phase 5 cuts over.
The MVP stays the source of truth for scraper behaviour, matching logic, and UX decisions
until each is ported.

## 1. Why we're rebuilding

The MVP proved the hard parts (anti-bot scraping D26, budget+sector search D27/D28,
matching D5/D17, the UX). Two things the MVP can't do:

1. **Geographic split.** The user is in Dubai where some portals are IP-blocked; scraping
   must run on a residential **Indian** IP. The UI must be reachable from anywhere.
2. **A single local SQLite file** can't be written by a remote scraper and read by a cloud
   UI at the same time.

v2 solves both with a **producer / central-store / consumer** architecture.

## 2. Locked decisions (2026-06-21)

| Area | Choice | Why |
|---|---|---|
| Database | **Supabase** (hosted Postgres + Auth) | Networked central store; managed; free tier; built-in auth + RLS |
| Backend | **Python / FastAPI** | Reuse `matcher.py` + the Patchright scraper as-is (Python is the irreplaceable IP); one server language |
| UI | **Next.js** (App Router) + shadcn/ui + Tailwind | "Real" frontend; we finally adopt the component lib the MVP deferred |
| Auth | **Supabase Auth**, per-user | Each user logs in; their shortlist / feedback / notes / requirements are private |
| Scraper host | **Physical box in India** | Relative's Mac/PC or a Raspberry Pi, residential IP + Chrome, auto-running on a timer |
| Repo | **Monorepo** | One place keeps schema + types in sync for a 2–3 person team |
| First portal | **MagicBricks only** | Tuned & working (D28). 99acres/Housing.com added later once verified from the India IP |

## 3. Target architecture

```
                         ┌─────────────────────────────┐
   India box (residential)│  apps/scraper (Python CLI)  │
   Chrome + Patchright    │  `prop-search scrape`       │
   systemd/launchd timer  │  scrape → match → upsert    │
   every 6h               └──────────────┬──────────────┘
                                          │ writes (service-role key)
                                          ▼
                         ┌─────────────────────────────┐
                         │   Supabase (Postgres + Auth) │  ← single source of truth
                         └──────────────┬───────▲───────┘
                       reads/writes via │       │ verifies JWT, scopes by user
                       service key      │       │
                                        ▼       │
   anywhere (Dubai)      ┌─────────────────────────────┐
   Vercel                │   apps/api (FastAPI)         │  ← business logic, user-facing
                         └──────────────┬──────────────┘
                                        │ REST + user JWT
                                        ▼
                         ┌─────────────────────────────┐
                         │   apps/web (Next.js)         │  ← login, browse, shortlist
                         └─────────────────────────────┘
```

Key separation:
- **Scraper → Supabase directly** (trusted producer, service-role key). Independent of API
  uptime — data keeps flowing even if the API is down.
- **UI ↔ API ↔ Supabase** for everything user-facing. The browser never holds the
  service-role key; it uses the Supabase anon key + the logged-in user's JWT.

## 4. Monorepo layout

```
prop-search/
├─ apps/
│  ├─ web/            # Next.js (App Router, shadcn/ui, Tailwind, TanStack Query)
│  ├─ api/            # FastAPI (auth, endpoints, reuses matcher)
│  └─ scraper/        # Python CLI: scrape → match → upsert; timer-driven
├─ packages/
│  ├─ core/           # shared PYTHON: matcher, property_types, normalization,
│  │                  #   scrapers/ (base + magicbricks), notifier  ← reused from MVP
│  └─ types/          # generated TS client from FastAPI OpenAPI (keeps web↔api in sync)
├─ supabase/
│  └─ migrations/     # SQL migrations = schema source of truth
├─ docs/              # DECISIONS.md, ARCHITECTURE.md, this plan
└─ tooling: pnpm workspace (web/types) + uv/poetry (api/scraper/core)
```

`apps/api` and `apps/scraper` both depend on `packages/core` (the Python business logic).
`apps/web` depends on `packages/types` (generated from the API).

## 5. Data model (Postgres) + multi-user

Ported from the MVP SQLite schema (`db.py`), with ownership added. Source of truth is
`supabase/migrations/`.

**Global (scraper-produced, read-only to users):**
- `listings` — same columns as MVP incl. `description`, `image_url`, `sector`,
  `approving_authority`, `first_seen_at`, `is_stale`, etc.
- `runs` — scrape-run history (for the System page).
- `portals` — portal config + last_run.
- `settings` — global scoring knobs (threshold, weights, tolerance). Kept **global** for
  v2 (one matching config; simpler than per-user).

**Per-user:**
- `requirements` — add `user_id uuid references auth.users`. Each user owns their queries.
- `matches` — `(requirement_id, listing_id, score)`; inherits user via `requirement`.
- `feedback` — PK `(user_id, listing_id)`; `verdict`, `reason`. Per-user.
- `tracking` — PK `(user_id, listing_id)`; `contacted_at`, `notes`. Per-user.

**Row-Level Security (RLS):**
- `requirements` / `matches` / `feedback` / `tracking`: `user_id = auth.uid()`.
- `listings` / `runs` / `portals` / `settings`: read to any authenticated user.
- Scraper uses the **service-role key** (bypasses RLS) to write global tables + matches.
- API verifies the user's Supabase JWT, then scopes every user query by `user_id`
  (explicit `WHERE`, with RLS as defense-in-depth).

**Matching ownership:** matching runs **in the scraper pipeline** (it already has
`matcher.py`). Each run: read all active requirements (across users) + global settings →
match against listings → upsert `matches`. Consequence: a requirement/settings edit only
re-matches on the next 6h run (same as today). *Future:* an API `POST /rematch` that runs
the matcher against existing listings on demand.

## 6. Component specs

### apps/scraper (build first — nothing works without data)
- Python CLI: `prop-search scrape [--once] [--portal magicbricks]`.
- Reuses `packages/core`: `scrapers/magicbricks.py` (D28 per-sector search), `matcher.py`,
  `property_types.py`, `notifier.py`.
- Reads requirements + settings from Supabase; writes `listings`, `matches`, `runs` via
  service-role key (asyncpg/psycopg or supabase-py).
- Headful Chrome + Patchright on the India box; persistent profile for the logged-in
  MagicBricks session (advertiser/owner data, D22).
- Scheduling: a **systemd timer** (Linux box) or **launchd** (Mac) firing every 6h —
  more robust than a long-lived APScheduler process.
- Telegram alerts fire from here (token in the box's `.env`).

### apps/api (FastAPI)
- Auth: verify Supabase JWT (JWKS); inject `user_id` per request.
- Endpoints (REST, all under `/v1`):
  - `requirements` — CRUD (user-scoped).
  - `matches` — list with filters (sector, show-verdict, sort, group-by-sector),
    pagination; joins feedback/tracking for the current user.
  - `feedback` — set/clear like/pass + reason (toggle semantics from MVP).
  - `tracking` — contacted toggle + notes.
  - `settings` — read/update global scoring knobs.
  - `system` — runs, portal status, parse-error summary.
- DB access: asyncpg/SQLAlchemy against the Supabase Postgres connection string.
- Hosting: Railway / Render / Fly.io. **Datacenter IP is fine here** — the API never
  scrapes, it only talks to Supabase.
- Auto-generates OpenAPI → `packages/types` TS client.

### apps/web (Next.js)
- Supabase Auth (email magic-link or password) via `supabase-js`.
- shadcn/ui + Tailwind. Port the MVP screens, keeping the UX decisions already made:
  - **Matches** — cards/table toggle, lightbox, like/pass + pass-reasons, contacted pill,
    NEW tag, Google-Maps sector links, sector filter + group-by-sector, sort.
  - **Shortlist** — Liked / Passed / Follow-ups (notes editor).
  - **Requirements** — CRUD table + modal (mirrors the redesign just shipped).
  - **System** — stat tiles, portals, run history.
  - **Settings** — scoring knobs.
- Data via TanStack Query against the API (user JWT in the Authorization header).
- Hosting: Vercel. Reachable from Dubai.

## 7. Security & secrets

| Secret | Lives on | Never on |
|---|---|---|
| Supabase **service-role** key | scraper box, API server | the browser / Next.js client |
| Supabase **anon** key + user JWT | Next.js client | — |
| Telegram bot token | scraper box | — |
| DB connection string | API server | the browser |

RLS enabled on every table. The browser can only ever reach user-scoped rows.

## 8. Hosting & cost (2–3 users)

| Component | Host | Cost |
|---|---|---|
| Supabase | managed | Free tier likely enough (scraper writing every 6h keeps the free project from auto-pausing) |
| API | Railway/Render/Fly | free–$7/mo |
| Web | Vercel | Hobby free |
| Scraper | India box | free (someone's home) + electricity |
| Telegram | — | free |

Effectively near-zero ongoing cost.

## 9. Phased rollout

- **Phase 0 — Foundations.** Monorepo scaffold + tooling; Supabase project; `supabase/migrations` (schema + RLS); Auth configured. *Done when:* migrations apply, a test user can log in.
- **Phase 1 — Scraper node.** Port the pipeline to write to Supabase; MagicBricks scrape → match → upsert end-to-end from the India box on a timer. *Done when:* a real run populates `listings`/`matches`/`runs` in Supabase.
- **Phase 2 — Backend API.** FastAPI with auth + all endpoints; OpenAPI → TS client. *Done when:* every endpoint returns correct user-scoped data (tested).
- **Phase 3 — Web UI.** Next.js + auth; port the 5 screens against the API. *Done when:* full browse/shortlist/requirements flows work logged-in.
- **Phase 4 — Deploy.** Supabase (managed), API (Railway/Render), Web (Vercel), scraper (India box timer). Telegram live. *Done when:* Dubai browser sees data scraped by the India box.
- **Phase 5 — Migrate & cut over.** One-time SQLite→Postgres migration (requirements + feedback worth keeping; listings repopulate on first scrape). Decommission Streamlit.

Build strictly in order — each phase's "done when" gates the next.

## 10. Reused from the MVP (don't rewrite)

`scrapers/base.py` + `scrapers/magicbricks.py` (D28), `matcher.py` (D5/D17/D24),
`property_types.py`, normalization helpers, `notifier.py`, and the SQLite schema in
`db.py` as the **basis** for the Postgres migrations. All UX/CSS decisions from the
Streamlit redesign inform the Next.js screens.

## 11. Open questions / risks

- **Portal reach from the India IP.** MagicBricks expected to keep working. 99acres /
  Housing.com unverified from an Indian residential IP — test before adding them.
- **India box reliability.** Uptime, reboots, sleep. Mitigate with systemd auto-restart /
  `caffeinate` on Mac; alert if no successful run in N hours.
- **Hot-linked image URLs** may expire. If so, mirror images to Supabase Storage (deferred).
- **Re-match latency** — edits apply on next 6h run; add `POST /rematch` if it feels slow.
- **Supabase free-tier limits** — fine at this scale; the 6h writes prevent auto-pause.

## 12. First concrete step

Phase 0: scaffold the monorepo, create the Supabase project, and write the initial
`supabase/migrations` (schema + RLS + auth). Everything downstream depends on the schema.
