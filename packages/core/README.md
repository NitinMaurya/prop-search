# packages/core (Python)

Shared Python business logic used by `apps/scraper` and `apps/api`. Ported from the MVP:

- `scrapers/` — `base.py` (Fetcher/Parser + registry) + `magicbricks.py` (D28 per-sector
  budget search, tuned & working). 99acres / Housing.com added later once verified.
- `matcher.py` — scoring (D5/D17/D24).
- `property_types.py` — category → portal URL + synonyms (D19).
- `notifier.py` — Telegram alerts.
- normalization helpers (price/size/sector).

The data-access layer is **not** here — in v2 the scraper and API talk to Supabase
directly (the MVP's `db.py` becomes the basis for `supabase/migrations` instead).
Populated in Phase 1.
