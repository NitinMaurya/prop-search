# Build plan & status

Stages: **planning ✅ → development (current) → verification**.
Build one full vertical slice (steps 1-5) before adding more scrapers (step 6), so the
core is proven before taking on scraper-maintenance burden.

Update the checkbox and "verify" note as each step lands.

Built via parallel agents: db.py first (frozen contract), then matcher/notifier/scrapers/app
in parallel, then scheduler.py integration. All modules import together; pipeline runs
end-to-end (verified with injected data). Remaining work is library install + live
selector tuning + the other 3 portals — see "Remaining" below.

- [x] **1. Scaffold + data layer** — `db.py` schema (incl. raw_listings, runs), 4 portals seeded.
  - Verified: `python3 db.py` creates 6 tables; dedup + round-trip smoke test passed.
- [x] **2. Streamlit requirement form** — full CRUD incl. owner + edit (`app.py` page 1, D9).
  - Verified: imports/parses; calls only existing db functions. *(Browser run pending — needs `pip install`.)*
- [~] **3. Scraper interface + 99acres plugin** — `scrapers/base.py` (Fetcher/Parser + registry) + `scrapers/nineacres.py`.
  - Done: code, normalization helpers (price/size/sector) unit-tested offline, self-registers.
  - PENDING: `pip install` + `playwright install chromium`, then **tune live SELECTORS** against real 99acres HTML (placeholders now). This is the irreducible per-site work.
- [x] **4. Matcher + dashboard** — `matcher.py` (D5 scoring) + matches view (`app.py` page 2).
  - Verified: matcher self-tests pass; pipeline produced a correct 1.0 match, excluded a bad one.
- [x] **5. Telegram notifier** — `notifier.py` (stdlib urllib, no extra dep).
  - Done: formats + sends; warns + skips when unconfigured. PENDING: real @BotFather token in `.env` to confirm a live message.
- [~] **6. Scheduler + remaining scrapers** — `scheduler.py` 4-stage loop + `runs` row + `--once`.
  - Done: scheduler runs LIVE end-to-end (2026-06-18). MagicBricks plugin built with
    selectors TUNED against live HTML — fetched 1 SRP, parsed 30 real Noida listings with
    working detail URLs, 0 errors. 99acres blocked by Akamai from this IP (D16, fails safe).
  - Plugins now registered for all 3 accessible portals: MagicBricks (TUNED, working),
    99acres + Housing.com (ready-to-tune SKELETONS — both blocked from this datacenter IP,
    D16). NoBroker left disabled (login walls). 
  - FINDING: live data exposed matcher over-leniency → tolerance ±30% + DB-configurable
    knobs (D17). Size = super built-up area (D18).
- [x] **7. System/Status page** — `app.py` page 3 (D15): per-portal, pipeline health, errors, run history.
  - Verified: imports; reads status_summary()/recent_runs(). *(Browser run pending — needs `pip install`.)*

## Anti-bot blocking — SOLVED (2026-06-19, D26)
Switched to **Patchright + headful real Chrome** on the user's residential IP. MagicBricks
now serves full SRPs end-to-end: 5 pages → 140 listings, 0 blocks, advertiser/owner detail
after a one-time manual login (session saved into the persistent profile). The 6h scheduler
must run on the user's Mac (not a cloud/datacenter host).
- Gotcha: a stale persistent profile causes `ERR_TOO_MANY_REDIRECTS` → delete
  `data/.pw-<portal>-profile` and re-login. (D26)
- **99acres + Housing.com remain dead:** the user's IP is blocked at the IP level (sites
  won't open even in a normal browser) — Patchright can't fix that. Stay disabled.

## Per-sector search — DONE (2026-06-20, D28)
A single city-wide budget search caps at ~90 listings (MagicBricks echoes deep pages), so
the fetcher now runs **one budget-filtered search per requirement sector** via
`&Locality=Sector-N`. Verified live: the 11-sector ₹3–5 Cr house requirement → **382
parsed / 0 errors / 58 new matches** in ~2 min (vs ~90 before). Falls back to one
city-wide search when the requirement has no sectors. See D28.

## Budget-filtered deep pagination — DONE (2026-06-19, D27)
MagicBricks now filters by budget server-side (`BudgetMin`+`BudgetMax` in the URL) and
paginates the in-budget set to exhaustion (retry/backoff past throttle stubs; stop when a
page adds no new listings). Verified: ₹3–4.5 Cr requirement → 88 parsed / 68 matches,
listings persisted (80 → 152 in DB). Known minor gap: one `page=N`+budget offset can
return an 8 KB stub and drop ~30 mid-list listings for that run (D27) — accepted.

## Remaining to be fully live
Deps are installed (.venv), Patchright active, Chrome detected. MagicBricks works end-to-end.
On the user's RESIDENTIAL machine:
1. Run `streamlit run app.py` and `python scheduler.py --once` to drive the app/pipeline.
2. ~~Tune 99acres + Housing.com~~ — blocked at IP level, not pursuing (D26).
3. Add a real Telegram token/chat id to `.env` to receive push alerts.
4. (Optional) NoBroker plugin — disabled by default (login walls / heaviest protection).
5. Confirm Q1 sectors (currently "all Noida"). Q2 tolerance ±30% + Q3 stale=3 are set and
   live-editable on the Settings page; D18 set size = super built-up area.

## Verification stage (after build)

- [ ] End-to-end dry run: submit requirement → run scheduler once → matches appear → Telegram fires.
- [ ] Dedup holds across portals (same kothi not duplicated).
- [ ] Stale marking works (remove a listing from source, confirm flagged after N runs).
- [ ] Scrapers fail gracefully (one portal down doesn't break the run).
