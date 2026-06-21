# apps/api (Phase 2)

FastAPI service between the web UI and Supabase. Verifies the user's Supabase JWT, scopes
every query by `user_id`, and serves REST under `/v1`. Reuses `packages/core` (matcher).

Endpoints (planned): `requirements` (CRUD), `matches` (filter/sort/group), `feedback`,
`tracking`, `settings`, `system`. Auto-generates OpenAPI → `packages/types` TS client.

Hosting: Railway / Render / Fly — **datacenter IP is fine** (the API never scrapes).
Config: see `.env.example`. Build details land in Phase 2 — see `docs/V2_PLAN.md` §6.
