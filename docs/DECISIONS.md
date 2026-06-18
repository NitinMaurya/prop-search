# Decisions

Locked product/technical decisions. ADR-lite: each entry = decision + why + implication.
Append new decisions; don't rewrite history. Newest at bottom.

---

## D1 — Scope: personal MVP, no scale
**Decision:** Build for 1 user (max 2-3), local machine only. No hosting, no auth, no
multi-tenant, no queue/broker, no cloud DB.
**Why:** Goal is to validate that the product solves the problem, not to scale.
**Implication:** SQLite + single process is fine. Reject any suggestion that adds infra.

## D2 — Stack: Python + Streamlit + SQLite
**Decision:** Streamlit serves both the requirement form and the matches dashboard.
SQLite is the data layer. Playwright for scraping, APScheduler for the 6h loop.
**Why:** Fastest path to a working form + dashboard in one tiny app; Python is the
natural ecosystem for scraping.
**Implication:** No separate frontend/backend split. One repo, few files.

## D3 — Portals are config in DB; parsers are code plugins
**Decision:** A `portals` table stores per-site config (name, base_url,
search_url_template, enabled). Each site's HTML parsing is a plugin in `scrapers/`
implementing the `base.py` interface, keyed by portal name.
**Why:** User wants to add/enable/retarget portals "on the fly." Config is editable in
DB without code; but parsing an arbitrary website cannot be config-only.
**Implication:** Enable/disable/retarget portal = DB edit. New unknown site = DB row +
~30-line parser plugin. Keep the plugin interface trivial to copy-paste. See
`docs/SCRAPER_GUIDE.md`.

## D4 — Target portals: 99acres, MagicBricks, Housing.com, NoBroker
**Decision:** Support all four, seeded into the `portals` table. Build 99acres first
(largest Noida inventory), then the rest one at a time.
**Why:** Coverage; user wants all of them, added dynamically.
**Implication:** NoBroker has heavier bot protection / login walls — lowest priority,
may stay disabled if too brittle.

## D5 — Matching: tolerance band + score
**Decision:** Not a strict cutoff. Score listings by weighted distance on size
(±tolerance %), budget (allow slight over-band as a near-match), and sector match.
Surface ranked near-misses.
**Why:** Strict filters miss good options in a thin resale market.
**Implication:** `matcher.py` owns scoring; threshold is configurable. Defaults:
size ±10%, budget soft-cap ~4.6cr.

## D6 — Alerts: Telegram bot
**Decision:** Push new matches to Telegram. Only *new, un-notified* matches above
threshold trigger a push (tracked by `matches.notified`).
**Why:** Free, instant, easy; a dashboard alone gets forgotten.
**Implication:** Needs bot token + chat id in `.env`. Setup via @BotFather (done at
build step 5).

## D7 — Dedup via fingerprint
**Decision:** Each listing gets `fingerprint = hash(normalized_price + size + sector +
fuzzy_title)`. Upsert by fingerprint; bump `last_seen_at` on re-sighting.
**Why:** Same kothi is posted by many brokers across portals and re-posted often.
Without dedup the user gets spammed.
**Implication:** Listing not seen for N runs → `is_stale = true` (sold/removed).

## D8 — "Kothi" maps to Independent House / Villa
**Decision:** Portals don't use the word "kothi." Map it to their "Independent House"
/ "Villa" / "Independent Floor" categories in search URLs and filters.
**Why:** Listing taxonomy on Indian portals.
**Implication:** Per-portal category mapping lives in the scraper plugin.

## D9 — Requirements are user data via full CRUD; not hardcoded
**Decision:** Every requirement is a row in the `requirements` table, created/edited/
deleted through the Streamlit form (full CRUD: create, list, **update**, deactivate/
delete). Each row has an `owner` field (name/email) so multiple users' queries coexist.
The scheduler loops over all active requirements — no requirement is ever hardcoded.
**Why:** Multiple users (2-3) must add/manage their own queries as data. The kothi
query (112/162 sqm, 4-4.5cr) is just the first row entered through the form.
**Implication:** No auth (D1) — `owner` is a plain text field, not a login. Telegram
notification can be addressed per owner later if needed (single chat for now).

## D10 — No multi-agent / autonomous-agent runtime
**Decision:** The product runtime stays a linear, deterministic pipeline (scrape →
dedup → score → notify) driven by the scheduler calling plain functions. No
multi-agent orchestration, no autonomous agents as product components.
**Why:** Control flow is fixed; there is no judgment/branching that needs agents.
Agents would add cost, latency, and non-determinism for zero benefit (D1: keep simple).
**Implication:** Reject suggestions to add agent frameworks to the runtime. Multi-agent
may be used at *build time* (developer orchestration) — that is separate and fine.

## D11 — Listing parsing: regex now, optional LLM extraction later
**Decision:** Parse/normalize scraped listings with CSS selectors + regex (step 3).
If that proves brittle, add a single, flag-gated LLM extraction step (raw card text →
{price, size_sqm, sector, type}) — one Claude call per listing, not a fleet.
**Why:** Parsing is the brittlest part. Regex is free/offline for the MVP; LLM is a
cheap robustness upgrade at this volume (a few listings / 6h) but adds an API-key
dependency, so it stays optional and off by default.
**Implication:** Keep scraper parsing isolated so an LLM extractor can slot in behind a
flag without touching the pipeline. Default path = regex, no API key required.

## D12 — Decoupled fetch → parse via a raw staging table
**Decision:** Two stages with a `raw_listings` staging table as the boundary.
(1) **Fetch:** store raw HTML/text per listing/page (portal, url, raw_html, fetched_at,
parse_status). (2) **Parse:** read unparsed raw rows → clean `listings`.
**Why:** Resilience. When a parser breaks (sites change often), re-parse from stored raw
without re-hitting the bot-protected site; can fix selectors and replay history.
**Implication:** Run sequentially for now — at this volume there is NO speed problem
(D1), so no threads/multiprocessing. But the design makes parallel parsing a trivial
later change (map over raw rows). Don't add concurrency until something is actually slow.

## D13 — Fetchers are pluggable behind the raw boundary
**Decision:** Split the old `Scraper` into two interfaces (base.py):
`Fetcher.fetch(requirement, portal_cfg) -> list[raw]` and
`Parser.parse(raw) -> listing dict`. The `raw_listings` table is the only contract
between them.
**Why:** A fetcher's job is just "produce raw rows." So fetchers are swappable per
portal anytime — Playwright for JS sites, plain HTTP/cloudscraper for easy ones, or a
manual-paste fetcher for fully-blocked sites — with zero change to parse/match/notify.
**Implication:** Plugins live as fetcher + parser keyed by portals.name. Mix freely.

## D14 — Use established libraries; don't hand-roll scraping
**Decision:** Playwright (fetch/JS) + playwright-stealth (anti-bot) + parsel or
BeautifulSoup (HTML→fields) + price-parser (₹/Cr/lakh → number). NOT Scrapy — it's a
heavyweight framework that would own the architecture and fight the
Streamlit+APScheduler+SQLite setup (and still needs scrapy-playwright for JS).
**Why:** Don't reinvent fetching, anti-bot, selection, or money parsing.
**Implication:** The only bespoke code per site is the selector map + search-URL pattern
(irreducible — no library knows a site's DOM). Everything else is library glue.

## D15 — Observability via a Streamlit "System" page + a runs table
**Decision:** The Streamlit app has three pages: (1) requirement form, (2) matches
dashboard, (3) **System/Status**. Status shows per-portal last-run + counts, pipeline
health (raw_listings pending/parsed/error), recent parse errors with URL, totals
(listings/stale/matches), and a run history. Backed by a small `runs` table; detailed
line logs stay in `logs/`.
**Why:** The system runs unattended every 6h on brittle scrapers — the user must see at
a glance whether it's working and whether a parser broke.
**Implication:** No external monitoring stack (Prometheus/Grafana) — all state is in
SQLite already, so the page is just queries (D1). scheduler.run_once() writes one `runs`
row per run.

## D16 — Anti-bot reality: 99acres is behind Akamai; needs a residential IP
**Decision:** Accept that 99acres (and likely MagicBricks) block automated access via
Akamai. The fetcher uses a persistent browser profile (cookie maturation), a homepage
warm-up, stealth v2, realistic headers, and explicit block detection (`_looks_blocked`).
Run headful (`PROP_HEADLESS=0`) on a **residential IP** for best results.
**Why:** Live test (2026-06-18) from this dev environment got an Akamai "Access Denied"
on the SRP and an empty homepage body — classic datacenter-IP block. The browser stack
itself works (example.com fetched fine), so the blocker is IP reputation + fingerprint.
**Implication:** Selector tuning is impossible until a real SRP page loads, which needs
the user's home machine / residential IP. The fetcher fails safe (returns [] on a block).

**Update 2026-06-18 (confirmed):** This dev environment is on a DATACENTER IP — Housing.com's
block page literally reported "Real Client IP: 2a09:bac6:... " (a hosting range). Live
results from here: **MagicBricks works** (lenient — fully tuned, 30 live listings parsed);
**99acres blocked** (Akamai "Access Denied"); **Housing.com blocked** ("Security Alert /
Request Blocked"). 99acres + Housing.com plugins are ready-to-tune SKELETONS — their real
selectors must be tuned on a residential IP. MagicBricks is the working reference plugin.

## D17 — Matcher tuning knobs are live-configurable in the DB
**Decision:** A `settings` (key, value) table holds the global matcher knobs — threshold,
w_size/w_price/w_sector, budget_softcap_pct, sector_miss_fit — plus stale_threshold_runs.
Editable live via a Streamlit "Settings" page. `matcher.py` stays PURE (no DB import):
the scheduler/app read `db.matcher_config()` and pass cfg into `score()/matches_for()`,
which merge it over `matcher.DEFAULTS`. Per-requirement `size_tolerance_pct` stays on
the requirement row (already dynamic).
**Why:** User wants to tune matching dynamically without code edits. Live data showed
the defaults needed adjusting (±10%→±30%, threshold sneak-through).
**Implication:** Changing a knob takes effect on the next scheduler run — no restart,
no redeploy. matcher purity preserved (still unit-testable standalone with DEFAULTS).

## D18 — Size = SUPER BUILT-UP area (independent house)
**Decision:** 112/162 sqm refer to **super built-up area**. Every scraper picks the size
field in this order: Super Area → Built-Up Area → Carpet Area → Plot Area (best-effort
fallback when super area isn't listed). Resolves the Q2 plot-vs-built-up sub-question.
**Why:** User confirmed the requirement is an independent house measured by super
built-up area.
**Implication:** All portal parsers must follow this priority (see SCRAPER_GUIDE).
Fallback to carpet/plot is approximate — flag in the listing if only a fallback was used
if this becomes a problem later.

## D19 — Property type is a user choice with synonym expansion
**Decision:** A requirement picks ONE category — **house / plot / apartment** (single
select; for two kinds make two requirements, D1). The category lives in
`requirements.property_type` (a key) and is expanded by `property_types.py` two ways:
(1) **search** — each portal gets a category-specific SRP URL (MagicBricks proptype
tokens, confirmed from the live `fetch-filter-data` API), so we fetch the right kind at
the source; (2) **matching** — `matcher.property_type_fit` recognises synonyms, so a
listing titled "Kothi"/"Villa"/"Independent House" all satisfy `house`. It is a GATE
(multiplier), not a weighted term: a wrong-category title multiplies the score by
`type_miss_fit` (default **0.0** → dropped). Ambiguous titles (no category word) are
left neutral (1.0) so we expand rather than wrongly exclude.
**Why:** User asked for a category choice that broadens the search to all the names a
type goes by (kothi/house/independent house, etc.), instead of one hardcoded URL.
**Implication:** Adding a portal means adding its category URLs to `property_types.py`.
Legacy free-text values (older rows stored `"kothi"`) map onto a key via `category_of()`.
`type_miss_fit` is a live DB knob (D17) on the Settings page — raise it above 0 to keep
wrong-type listings as low-ranked instead of dropping them.

## D20 — MagicBricks JSON API (auth) + images/advertiser
**Decision:** When `MB_COOKIE` (a logged-in MagicBricks session, from `.env`) is set, the
MagicBricks fetcher calls the **`mbsrp/propertySearch.html` JSON API** instead of scraping
HTML; the Playwright HTML path remains the no-cookie fallback. The Parser auto-detects
JSON (`{`-prefixed raw) vs HTML. JSON carries **images** (`image`/`allImgPath`) and
**advertiser** (`companyname`/`oname` + `userType`) directly, stored in new
`listings.image_url` / `listings.advertiser` columns (added via idempotent `ALTER TABLE`
migration in `init()`). Shown in the Matches table (ImageColumn + Advertiser).
propertyType IDs (confirmed live): house=`10001,10017`, plot=`10000`,
apartment=`10002,10003,10021,10022`. Size = `coveredArea` × `covAreaUnit` factor → sqm
(D18); `12801`=sqm, `12800`=sqft, `12803`=sqyrd.
**Why:** JSON is far more robust than CSS selectors and is the only reliable source of
images + advertiser (HTML cards lazy-load images; contacts sit behind login). The user
provided a logged-in session and live API responses to build against.
**Implication:** `MB_COOKIE` goes in `.env` (gitignored), never committed; cookies expire
so the user refreshes them periodically. Can't be exercised from a datacenter IP (Akamai,
D16) — runs on the user's residential machine. Phone numbers still require per-listing
OTP and are out of scope.

---

## Open questions (resolve before/while building)

- **Q1 — Noida sectors:** Which sectors to target? (user to confirm; default = all Noida)
- **Q2 — Size values:** 112 and 162 sqm confirmed; tolerance default **±30%** (set
  2026-06-18 after live MagicBricks data showed ±10% was too tight). OPEN sub-question:
  do 112/162 sqm mean PLOT area or BUILT-UP/carpet area? Listings mostly show carpet/
  super area; the matcher compares against whatever the parser picks (Plot>Super>Carpet).
- **Q3 — Stale threshold:** How many missed runs marks a listing stale? (default: 3)
