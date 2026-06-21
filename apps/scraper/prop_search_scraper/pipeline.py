"""One scrape cycle: fetch → parse → upsert → match → notify, writing to Supabase.

Ports the v1 scheduler.run_once() pipeline (D12) to the v2 Store. Fetch+parse happen
in-memory (no raw_listings staging table in v2). Resilient: one portal / page / match
failing never aborts the run.
"""

import logging

from prop_search_core import matcher, notifier
from prop_search_core.scrapers import base as scrapers

log = logging.getLogger("scraper.pipeline")

HOURS_PER_RUN = 6


def _is_noida_authority(listing: dict) -> bool:
    """True if a NOIDA-Authority, non-freehold property (D21)."""
    auth = str(listing.get("approving_authority") or "").strip().upper()
    ownership = str(listing.get("ownership") or "").strip().lower()
    return auth == "NOIDA" and ownership != "freehold"


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def run_once(store, only_portal: str | None = None) -> dict:
    """Run one full pipeline cycle against the Store. Returns the run counts."""
    run_id = store.start_run()
    counts = {"portals_run": 0, "raw_fetched": 0, "parsed_ok": 0,
              "parse_errors": 0, "new_matches": 0, "notified": 0}
    try:
        requirements = store.active_requirements()
        portals = store.enabled_portals(only=only_portal)
        log.info("run %s: %d enabled portals x %d active requirements",
                 run_id, len(portals), len(requirements))
        if not requirements:
            log.warning("no active requirements — nothing to match")

        # ---- FETCH + PARSE (in-memory) ------------------------------------------
        for portal in portals:
            fetcher = scrapers.get_fetcher(portal["name"])
            parser = scrapers.get_parser(portal["name"])
            if fetcher is None or parser is None:
                log.warning("no plugin for portal %r; skipping", portal["name"])
                continue
            counts["portals_run"] += 1
            for req in requirements:
                try:
                    raws = fetcher.fetch(req, portal) or []
                except Exception as e:  # noqa: BLE001 - one portal must not abort the run
                    log.error("fetch failed %s / req %s: %s",
                              portal["name"], req["id"], e)
                    continue
                for raw in raws:
                    counts["raw_fetched"] += 1
                    try:
                        listings = parser.parse(raw) or []
                    except Exception as e:  # noqa: BLE001
                        log.error("parse failed (%s): %s", portal["name"], e)
                        counts["parse_errors"] += 1
                        continue
                    for listing in listings:
                        listing["portal_id"] = portal["id"]
                        try:
                            store.upsert_listing(listing)
                            counts["parsed_ok"] += 1
                        except Exception as e:  # noqa: BLE001
                            log.error("upsert failed: %s", e)
                            counts["parse_errors"] += 1
            store.update_portal_last_run(portal["id"])

        # ---- STALE + MATCH ------------------------------------------------------
        cfg = store.matcher_config()
        try:
            stale_runs = int(float(store.setting("stale_threshold", 3)))
        except (TypeError, ValueError):
            stale_runs = 3
        store.mark_stale(stale_runs, HOURS_PER_RUN)

        listings = store.active_listings()
        if _truthy(store.setting("noida_authority_only", "1")):  # D21
            before = len(listings)
            listings = [l for l in listings if _is_noida_authority(l)]
            log.info("NOIDA-authority filter: %d -> %d", before, len(listings))

        for req in requirements:
            for listing, sc in matcher.matches_for(req, listings, cfg):
                try:
                    if store.record_match(req["id"], listing["id"], sc):
                        counts["new_matches"] += 1
                except Exception as e:  # noqa: BLE001
                    log.error("record_match failed req %s listing %s: %s",
                              req["id"], listing["id"], e)

        # ---- NOTIFY -------------------------------------------------------------
        pending = store.unnotified_matches()
        sent_ids = notifier.send_matches(pending)
        for match_id in sent_ids:
            store.mark_notified(match_id)
        counts["notified"] = len(sent_ids)

        store.finish_run(run_id, **counts)
        log.info("run %s done: %s", run_id, counts)
        return counts
    except Exception as e:  # noqa: BLE001 - record the failure, don't crash the box's timer
        log.exception("run %s aborted", run_id)
        store.finish_run(run_id, error=str(e), **counts)
        return counts
