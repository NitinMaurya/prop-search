# prop-search

Local tool that scrapes Noida property portals every 6h, matches listings against
user-defined requirements, and pushes new matches to Telegram. Personal MVP, 2-3 users,
runs locally. **Keep it simple — do not over-engineer or add infra for scale.**

## How to use this repo (for AI agents)

Read only what the task needs. This file routes you to the right doc:

| If you are working on...        | Read first                          |
|---------------------------------|-------------------------------------|
| Any non-trivial decision / "why"| `docs/DECISIONS.md`                 |
| Data model, tables, flow        | `docs/ARCHITECTURE.md`              |
| What to build next / status     | `docs/PLAN.md`                      |
| Adding or fixing a scraper      | `docs/SCRAPER_GUIDE.md`             |

Do NOT read all source files to orient — the placeholder docstring in each file states
its contract. Open a file only when you will edit it.

## Stack

Python · Streamlit (form + dashboard) · SQLite · Playwright (scraping) · APScheduler
(6h loop) · python-telegram-bot (alerts). All local; no hosting/deploy.

## Commands

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium      # one-time, for scrapers
streamlit run app.py             # form + dashboard
python scheduler.py              # run the 6h scrape/match/notify loop
```

## Conventions

- One scraper plugin per portal in `scrapers/`, implementing the `base.py` interface.
  Portal *config* lives in the `portals` DB table; portal *parsing* lives in code.
- SQLite file at `data/prop_search.db`. Schema is owned by `db.py` — change it there.
- Secrets (Telegram token/chat id) go in `.env`, never committed.
- Log scrape runs to `logs/`. Keep functions small; prefer clarity over cleverness.

## Status

See `docs/PLAN.md` for the live build checklist. Update it as steps complete.
