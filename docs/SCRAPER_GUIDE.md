# Adding / fixing a scraper

This is the repeatable, highest-churn task (sites change HTML often). Fetch and parse
are decoupled (D12/D13), so most "the scraper broke" fixes touch only the Parser and can
be tested by replaying stored raw rows — no re-fetching the bot-protected site.

## The contract (`scrapers/base.py`)

Each portal has a **Fetcher** and a **Parser** keyed by `portals.name`:

```python
class Fetcher:
    name = "99acres"
    def fetch(self, requirement, portal_cfg) -> list[dict]:  # [{url, raw_html}, ...]
        ...  # Playwright + stealth; no parsing here

class Parser:
    name = "99acres"
    def parse(self, raw) -> list[dict]:                      # one raw page -> many cards
        ...  # parsel/bs4 + price-parser; return [] if nothing parses, skip bad cards
```

Parser output keys:
`external_id, url, title, price (int rupees), size_sqm (float), sector, raw_location,
posted_date (or None)`. The pipeline computes `fingerprint`, timestamps, and upserts.

**Fixing a broken parser:** edit the Parser, then `db.reset_raw_pending(portal_id)` and
rerun stage 2 — replays against stored raw, no site hit. **Swapping a fetcher** (e.g.
Playwright → HTTP/cloudscraper for an easy site, or a manual-paste fetcher for a blocked
one): change only the Fetcher; parser and pipeline are untouched.

## Steps to add a new portal

1. Insert a row in `portals` (DB): `name`, `base_url`, `search_url_template`
   (placeholders `{sector} {price_min} {price_max} {size}`), `enabled=1`.
2. Copy an existing plugin in `scrapers/` to `scrapers/<name>.py`; set `name` on both
   the Fetcher and Parser.
3. Map "kothi" → that site's category (Independent House / Villa / Floor) in the URL.
4. Update the CSS/XPath selectors in the Parser for that site's result cards.
5. Register the plugin (loader maps `portals.name` → (Fetcher, Parser)).
6. Test each stage in isolation:
   fetch → `Fetcher().fetch(REQ, CFG)[:1]` (inspect raw_html);
   parse → feed a saved raw row to `Parser().parse(raw)` (no site hit needed).

## Scraping rules of thumb (Indian portals = bot-protected)

- Use Playwright headful-like settings (realistic UA, viewport); wait for listing
  selectors, not fixed sleeps.
- 6h cadence is gentle — don't hammer. Add small randomized delays between pages.
- Parse defensively: missing price/size → skip the card, log it, continue.
- When a scraper returns 0 results unexpectedly, the site likely changed layout →
  re-inspect selectors. This is expected maintenance, not a bug in the pipeline.
- Log each run (count parsed/skipped) to `logs/`.

## Price normalization

Indian listings use "₹4.25 Cr", "4,25,00,000", "4.5 Crore". Normalize all to integer
rupees in the plugin. Size may be in sq.ft or sq.m / sq.yd — convert to **sqm**
(1 sq.ft = 0.092903 sqm; 1 sq.yd = 0.836127 sqm).
