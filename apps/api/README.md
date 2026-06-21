# apps/api (Phase 2 ✅ built)

FastAPI service between the web UI and Supabase. Verifies the user's Supabase JWT (HS256,
`Authorization: Bearer`), scopes every query by `user_id`, serves REST under `/v1`.
Connects to Supabase Postgres directly (postgres role, bypasses RLS); RLS is
defense-in-depth.

## Layout
- `config.py` — env (`DATABASE_URL`, `SUPABASE_JWT_SECRET`, `WEB_ORIGIN`).
- `auth.py` — `get_user_id` dependency (verifies the JWT → `sub`).
- `db.py` — psycopg connection pool + user-scoped data functions.
- `schemas.py` — Pydantic request/response models.
- `routers.py` — all `/v1` endpoints (filtering/sorting reuse `packages/core`).
- `main.py` — app + CORS + `/health`.

## Endpoints (`/v1`)
`requirements` (GET/POST/PATCH/DELETE) · `matches` (GET; `requirement_id`, `show`, `sort`,
`sectors` filters) · `feedback` (POST) · `tracking/contacted` (POST) · `tracking/notes`
(PUT) · `settings` (GET/PUT) · `system` (GET). Plus `/health`.

## Setup & run
```bash
uv venv --python 3.12
uv pip install -e ../../packages/core -e .
cp .env.example .env            # DATABASE_URL + SUPABASE_JWT_SECRET + WEB_ORIGIN
uv run prop-search-api          # uvicorn on :8000  (docs at /docs)
```

## Contract
`packages/types/openapi.json` is the OpenAPI snapshot (regenerate after endpoint changes:
`python -c "import json,prop_search_api.main as m; json.dump(m.app.openapi(), open('../../packages/types/openapi.json','w'), indent=2)"`).
The web app generates its TS client from it (Phase 3).

Hosting: Railway / Render / Fly — datacenter IP is fine (the API never scrapes).
