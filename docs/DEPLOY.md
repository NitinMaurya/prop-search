# Deploying prop-search v2 (Phase 4)

Four pieces. Web + API are cloud-hosted; the scraper runs on a residential India box.

```
[India box] scraper  --writes-->  Supabase (DB+Auth)  <--reads--  API (Render)  <--  Web (Vercel)  <--  you
```

## 0. Region (do this first — it's the perf fix)
Latency from Dubai to a far Supabase region is the main slowness. Best setup for a Dubai
user + India scraper: **Supabase in Mumbai (ap-south-1)** and the **API in the same/closest
region**. If your project is elsewhere, recreating it in Mumbai is worth it — re-seed with:
```
# against the new project's DATABASE_URL:
python scripts/apply_migrations.py        # 0001..0003
python scripts/migrate_sqlite.py          # listings/settings/runs (+ per-user after login)
```

## 1. API → Render (recommended; Railway/Fly work too)
The API is containerized (`apps/api/Dockerfile`) and never scrapes, so any datacenter is fine.

1. Render → **New → Web Service** → connect the GitHub repo, branch `v2-overhaul`.
2. **Runtime: Docker**, **Dockerfile path:** `apps/api/Dockerfile`, **Docker build context: `.`** (repo root).
3. **Region:** the same/closest to your Supabase region.
4. **Environment variables:**
   - `DATABASE_URL` = Supabase Postgres URI (use the **Session pooler** string for hosted apps)
   - `SUPABASE_URL` = `https://<ref>.supabase.co`
   - `WEB_ORIGIN` = your Vercel URL (e.g. `https://prop-search.vercel.app`)
5. Deploy → note the API URL (e.g. `https://prop-search-api.onrender.com`). Check `/health`.

> Railway/Fly: same Dockerfile, set the same env vars + root build context.

## 2. Web → Vercel
1. Vercel → **Add New → Project** → import the repo.
2. **Root Directory: `apps/web`** (it's self-contained; framework auto-detected as Next.js).
3. **Environment variables:**
   - `NEXT_PUBLIC_SUPABASE_URL` = `https://<ref>.supabase.co`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY` = the **publishable** key
   - `NEXT_PUBLIC_API_BASE_URL` = `https://<your-render-api>/v1`
4. Deploy → note the Vercel URL, then set it as `WEB_ORIGIN` on the API (step 1.4) and redeploy the API so CORS allows it.

## 3. Supabase Auth redirect URLs
Dashboard → Authentication → URL Configuration → add your Vercel origin to **Site URL** and
**Redirect URLs** (e.g. `https://prop-search.vercel.app/**`) so Google/email login redirects work in prod.

## 4. Scraper → India box (not cloud)
A datacenter IP is blocked by the portals, so the scraper runs on a residential India
machine (relative's Mac/PC or a Pi). See `apps/scraper/README.md`:
```
uv venv --python 3.12 && uv pip install -e ../../packages/core -e .
uv run patchright install chrome
cp .env.example .env    # DATABASE_URL (+ Telegram)
uv run prop-search-scrape
```
Schedule every 6h with a **systemd timer** (Linux) or **launchd** (macOS).

## 5. Contact button (per user, optional)
The **Contact** button drives MagicBricks' real "Contact Owner" in each user's *own* logged-in
browser via a small userscript (no server worker, no extra infra). Each user installs it once
via Tampermonkey — see `tools/README.md`. Without it, the card still deep-links to the listing
to click manually.

## Cost
Supabase free · Vercel Hobby free · Render free–$7/mo · India box = electricity. ~Near-zero.
