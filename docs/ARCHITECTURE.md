# Architecture

## Flow (decoupled fetch → parse, D12/D13)

```
Streamlit form  ──save──>  requirements (DB)
                                  │
APScheduler (every 6h) ───────────┤
                                  ▼
  STAGE 1 FETCH — for each enabled portal × active requirement:
      Fetcher.fetch(req, portal)  (Playwright + stealth, search URL by sector/price/size)
                          │
                store raw rows → raw_listings (parse_status='pending')   ← contract boundary
                          │
  STAGE 2 PARSE — for each pending raw row (sequential now; trivially parallel later):
      Parser.parse(raw)  (parsel/bs4 + price-parser → clean fields)
                          │
              dedup by fingerprint → upsert into listings (DB); mark raw parsed
                          │
  STAGE 3 MATCH — matcher scores listings vs requirements → matches (DB)
                          │
  STAGE 4 NOTIFY — new matches (notified=false, score≥threshold) → Telegram; mark notified

Streamlit dashboard reads matches+listings → ranked view (always available)
```

Fetchers and parsers are swappable per portal behind `raw_listings` (D13): a broken
parser re-runs on stored raw without re-fetching; a blocked site can use a different
fetcher with no downstream change.

## Modules & contracts

| File              | Owns                                                                 |
|-------------------|----------------------------------------------------------------------|
| `db.py`           | SQLite connection, schema (DDL), all read/write queries. Single source of truth for the data model. |
| `app.py`          | Streamlit UI, 4 pages: requirement form (full CRUD), matches dashboard, System/Status (D15), Settings (live matcher knobs — D17). |
| `scrapers/base.py`| `Fetcher.fetch(requirement, portal_cfg) -> list[raw]` and `Parser.parse(raw) -> list[listing]` (one raw page → many cards). The `raw_listings` table is the boundary between them (D13). Plus a plugin registry: `register`/`get_fetcher`/`get_parser`. |
| `scrapers/*.py`   | One fetcher + parser per portal. Fetcher builds search URL + drives Playwright→raw; parser turns raw HTML into listing dicts via parsel/price-parser. |
| `matcher.py`      | `score(listing, requirement) -> float` and selection of matches above threshold. |
| `notifier.py`     | `send_matches(matches)` → Telegram. Reads token/chat id from env. |
| `scheduler.py`    | APScheduler job: orchestrates scrape → dedup → match → notify every 6h. Also runnable once for testing. |

## Data model (SQLite)

Schema is authoritative in `db.py`. Summary:

### requirements
| col | type | notes |
|-----|------|-------|
| id | INTEGER PK | |
| owner | TEXT | who submitted it (name/email) — multi-user, no auth (D9) |
| property_type | TEXT | e.g. "kothi" |
| sizes_sqm | TEXT | JSON list, e.g. [112,162] |
| size_tolerance_pct | REAL | default 10 |
| budget_min | INTEGER | rupees |
| budget_max | INTEGER | rupees (soft cap) |
| sectors | TEXT | JSON list of Noida sectors, empty = all |
| active | INTEGER | 0/1 |
| created_at | TEXT | ISO |

### portals
| col | type | notes |
|-----|------|-------|
| id | INTEGER PK | |
| name | TEXT UNIQUE | matches scraper plugin key, e.g. "99acres" |
| base_url | TEXT | |
| search_url_template | TEXT | placeholders: {sector} {price_min} {price_max} {size} |
| enabled | INTEGER | 0/1 |
| last_run_at | TEXT | ISO |

### raw_listings  (staging boundary, D12)
| col | type | notes |
|-----|------|-------|
| id | INTEGER PK | |
| portal_id | INTEGER FK | which fetcher produced it |
| url | TEXT | listing/page URL |
| raw_html | TEXT | raw payload as fetched (also keep raw text if cheaper) |
| fetched_at | TEXT | ISO |
| parse_status | TEXT | 'pending' / 'parsed' / 'error' |
| parse_error | TEXT | last error message if status='error' (for replay) |

Parsing reads `parse_status='pending'`, writes `listings`, flips status. Re-parsing a
site after a selector fix = reset matching rows to 'pending' and rerun stage 2.

### listings
| col | type | notes |
|-----|------|-------|
| id | INTEGER PK | |
| portal_id | INTEGER FK | |
| external_id | TEXT | portal's own id if available |
| url | TEXT | listing link (what the user clicks) |
| title | TEXT | |
| price | INTEGER | rupees |
| size_sqm | REAL | |
| sector | TEXT | normalized, e.g. "Sector 50" |
| raw_location | TEXT | as scraped |
| posted_date | TEXT | if available |
| fingerprint | TEXT | dedup key (see D7) — UNIQUE |
| first_seen_at | TEXT | ISO |
| last_seen_at | TEXT | ISO |
| is_stale | INTEGER | 0/1 |

### runs  (observability, D15)
| col | type | notes |
|-----|------|-------|
| id | INTEGER PK | |
| started_at | TEXT | ISO |
| finished_at | TEXT | ISO, null while running |
| portals_run | INTEGER | # portals attempted |
| raw_fetched | INTEGER | rows added to raw_listings |
| parsed_ok | INTEGER | listings upserted |
| parse_errors | INTEGER | raw rows that failed parsing |
| new_matches | INTEGER | matches created this run |
| notified | INTEGER | Telegram messages sent |
| error | TEXT | run-level error if the whole run aborted |

One row per scheduler.run_once(). The System page reads this for run history; live
detail goes to logs/.

### matches
| col | type | notes |
|-----|------|-------|
| id | INTEGER PK | |
| requirement_id | INTEGER FK | |
| listing_id | INTEGER FK | |
| score | REAL | 0..1 |
| notified | INTEGER | 0/1 |
| created_at | TEXT | ISO |

UNIQUE(requirement_id, listing_id) so a listing matches a requirement once.

## Matching (matcher.py)

`score = w_size * size_closeness + w_price * price_fit + w_sector * sector_fit`
- size_closeness: 1.0 at exact target size, decays past tolerance band.
- price_fit: 1.0 inside [budget_min, budget_max], decays above soft cap.
- sector_fit: 1.0 if listing sector in requirement sectors (or requirement = all).
Default weights and threshold defined as constants in `matcher.py`.
