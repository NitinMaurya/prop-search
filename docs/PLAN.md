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

## Remaining to be fully live
Deps are installed (.venv) and Chromium is downloaded. MagicBricks works end-to-end now.
On the user's RESIDENTIAL machine:
1. Run `streamlit run app.py` and `python scheduler.py --once` to drive the app/pipeline.
2. Tune 99acres + Housing.com live SELECTORS — fetch from the residential IP, inspect
   `raw_html`, fix the `SELECTORS` blocks (both are skeletons; MagicBricks is the model).
3. Add a real Telegram token/chat id to `.env` to receive push alerts.
4. (Optional) NoBroker plugin — disabled by default (login walls / heaviest protection).
5. Confirm Q1 sectors (currently "all Noida"). Q2 tolerance ±30% + Q3 stale=3 are set and
   live-editable on the Settings page; D18 set size = super built-up area.

## Verification stage (after build)

- [ ] End-to-end dry run: submit requirement → run scheduler once → matches appear → Telegram fires.
- [ ] Dedup holds across portals (same kothi not duplicated).
- [ ] Stale marking works (remove a listing from source, confirm flagged after N runs).
- [ ] Scrapers fail gracefully (one portal down doesn't break the run).
