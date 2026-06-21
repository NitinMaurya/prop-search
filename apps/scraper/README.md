# apps/scraper (Phase 1 ✅ built)

Python CLI that runs on the residential **India box**. Reuses `packages/core` (scrapers,
matcher, property types, notifier). One cycle = read active requirements + settings from
Supabase → scrape MagicBricks (D28 per-sector) with Chrome/Patchright → match → upsert
`listings` + `matches` + a `runs` row to Supabase → Telegram alerts for new matches.

## Layout
- `store.py` — Postgres data layer (psycopg, direct `DATABASE_URL`, bypasses RLS).
- `pipeline.py` — `run_once()` (ported from the v1 scheduler, D12).
- `cli.py` — `prop-search-scrape` entry point (runs one cycle).

## Setup (on the India box)
Requires Google Chrome installed + a residential India IP.
```bash
uv venv --python 3.12
uv pip install -e ../../packages/core -e .
uv run patchright install chrome     # one-time browser setup
cp .env.example .env                 # fill in DATABASE_URL (+ Telegram)
```

## Run
```bash
uv run prop-search-scrape                 # one cycle, all enabled portals
uv run prop-search-scrape --portal magicbricks
```
First run only: open the MagicBricks login once in the persistent profile so advertiser/
owner data is available (D22) — the profile lives under `PROP_DATA_DIR`.

## Schedule (every 6h) — pick one
**launchd (macOS):** a `StartInterval 21600` agent calling `prop-search-scrape`.
**systemd (Linux):** a `prop-search.service` (oneshot) + `prop-search.timer`
(`OnCalendar=*-*-* 00,06,12,18:00`). systemd auto-restarts and journals output.

A timer is more robust than a long-lived in-process scheduler (survives reboots/crashes).
See `docs/V2_PLAN.md` §6 / §9.
