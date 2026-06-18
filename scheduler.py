"""Scheduler — the 6h scrape -> dedup -> match -> notify loop (build step 6).

Decoupled stages (D12); records one `runs` row per cycle for observability (D15).
Also runnable once for testing:  python scheduler.py --once

run_once():
  STAGE 1 FETCH  — each enabled portal x active requirement -> raw_listings (D12)
  STAGE 2 PARSE  — each pending raw page -> many listings, dedup-upsert (D7); replayable
  STAGE 3 MATCH  — score active listings vs each requirement (D5) -> matches
  STAGE 4 NOTIFY — send un-notified matches to Telegram (D6), mark notified

Resilience: one portal / one raw page / one match failing never aborts the run
(per-item try/except, logged to logs/). A parse failure leaves the raw row
parse_status='error' for later replay via db.reset_raw_pending().
"""

import argparse
import logging
import os

import db
import matcher
import notifier
from scrapers import base as scrapers

HOURS_PER_RUN = 6
STALE_THRESHOLD_RUNS = 3  # Q3

# ------------------------------------------------------------------------------ logging
_LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(_LOG_DIR, "scheduler.log")),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("scheduler")


def run_once() -> dict:
    """Run one full pipeline cycle. Returns the counts recorded on the `runs` row."""
    db.init()
    run_id = db.start_run()
    counts = {"portals_run": 0, "raw_fetched": 0, "parsed_ok": 0,
              "parse_errors": 0, "new_matches": 0, "notified": 0}
    try:
        requirements = db.list_requirements(active_only=True)
        portals = db.list_enabled_portals()
        log.info("run %s: %d enabled portals x %d active requirements",
                 run_id, len(portals), len(requirements))

        # ---- STAGE 1 FETCH ------------------------------------------------------
        for portal in portals:
            fetcher = scrapers.get_fetcher(portal["name"])
            if fetcher is None:
                log.warning("no scraper plugin registered for portal %r; skipping",
                            portal["name"])
                continue
            counts["portals_run"] += 1
            for req in requirements:
                try:
                    raws = fetcher.fetch(req, portal) or []
                except Exception as e:  # noqa: BLE001 - one portal must not abort the run
                    log.error("fetch failed for %s / req %s: %s",
                              portal["name"], req["id"], e)
                    continue
                for raw in raws:
                    db.add_raw(portal["id"], raw.get("url"), raw.get("raw_html"))
                    counts["raw_fetched"] += 1
            db.update_portal_last_run(portal["id"])

        # ---- STAGE 2 PARSE (sequential now; trivially parallel later — D12) ------
        for raw in db.pending_raw():
            parser = scrapers.get_parser(raw["portal_name"])
            if parser is None:
                db.mark_raw_error(raw["id"], "no parser plugin registered")
                counts["parse_errors"] += 1
                continue
            try:
                listings = parser.parse(raw) or []
                for listing in listings:
                    listing["portal_id"] = raw["portal_id"]  # parser doesn't set this
                    db.upsert_listing(listing)
                db.mark_raw_parsed(raw["id"])
                counts["parsed_ok"] += len(listings)
            except Exception as e:  # noqa: BLE001 - leave row 'error' for replay (D12)
                log.error("parse failed for raw %s (%s): %s",
                          raw["id"], raw["portal_name"], e)
                db.mark_raw_error(raw["id"], str(e))
                counts["parse_errors"] += 1

        cfg = db.matcher_config()  # live tuning knobs from the settings table (D17)
        stale_runs = int(db.get_setting("stale_threshold_runs", STALE_THRESHOLD_RUNS))
        db.mark_stale(threshold_runs=stale_runs)

        # ---- STAGE 3 MATCH ------------------------------------------------------
        listings = db.list_active_listings()
        for req in requirements:
            for listing, sc in matcher.matches_for(req, listings, cfg):
                try:
                    db.record_match(req["id"], listing["id"], sc)
                    counts["new_matches"] += 1  # OR IGNORE dedups; approx new count
                except Exception as e:  # noqa: BLE001
                    log.error("record_match failed req %s listing %s: %s",
                              req["id"], listing["id"], e)

        # ---- STAGE 4 NOTIFY -----------------------------------------------------
        pending = db.unnotified_matches()
        sent_ids = notifier.send_matches(pending)
        for match_id in sent_ids:
            db.mark_notified(match_id)
        counts["notified"] = len(sent_ids)

        db.finish_run(run_id, **counts)
        log.info("run %s done: %s", run_id, counts)
        return counts
    except Exception as e:  # noqa: BLE001 - record a run-level failure, don't crash the loop
        log.exception("run %s aborted", run_id)
        db.finish_run(run_id, error=str(e), **counts)
        return counts


def start_schedule() -> None:
    """Run forever, firing run_once() every HOURS_PER_RUN hours (APScheduler)."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        log.error("apscheduler not installed; run `pip install -r requirements.txt` "
                  "or use --once. Running a single cycle now instead.")
        run_once()
        return
    sched = BlockingScheduler()
    sched.add_job(run_once, "interval", hours=HOURS_PER_RUN,
                  next_run_time=__import__("datetime").datetime.now())
    log.info("scheduler started: running every %dh (Ctrl-C to stop)", HOURS_PER_RUN)
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("scheduler stopped")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="prop-search scrape/match/notify loop")
    ap.add_argument("--once", action="store_true",
                    help="run a single cycle and exit (default: run every 6h)")
    args = ap.parse_args()
    if args.once:
        run_once()
    else:
        start_schedule()
