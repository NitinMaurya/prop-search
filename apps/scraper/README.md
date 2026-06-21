# apps/scraper (Phase 1)

Python CLI that runs on the residential **India box**. Reuses `packages/core` (scrapers,
matcher, property types, notifier).

Pipeline per run: read active requirements + settings from Supabase → scrape MagicBricks
(D28 per-sector) with Chrome/Patchright → match → upsert `listings` + `matches` + a `runs`
row to Supabase (service-role key) → Telegram alerts for new matches.

Planned:
- `prop-search scrape --once [--portal magicbricks]`
- A **systemd timer** (Linux) / **launchd** (macOS) firing every 6h.

Config: see `.env.example`. Requires Google Chrome installed + a residential India IP.
Build details land in Phase 1 — see `docs/V2_PLAN.md` §6 / §9.
