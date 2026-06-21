"""CLI entry point: `prop-search-scrape [--portal magicbricks]`.

Runs ONE cycle and exits — the 6h cadence is owned by a systemd timer / launchd job on
the India box (more robust than a long-lived in-process scheduler). See apps/scraper/README.
"""

import argparse
import logging
import os
import sys

from .pipeline import run_once
from .store import Store

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("scraper")

    ap = argparse.ArgumentParser(description="prop-search v2 scraper — one cycle")
    ap.add_argument("--portal", help="only this portal (e.g. magicbricks)")
    ap.add_argument("--once", action="store_true",
                    help="run a single cycle (default; timer handles the 6h cadence)")
    args = ap.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        log.error("DATABASE_URL is not set (see apps/scraper/.env.example)")
        return 2

    store = Store(dsn)
    try:
        counts = run_once(store, only_portal=args.portal)
    finally:
        store.close()

    new = counts.get("new_matches", 0)
    print(f"✓ scrape complete — {counts.get('parsed_ok', 0)} listings, "
          f"{new} new match{'es' if new != 1 else ''}, "
          f"{counts.get('notified', 0)} notified "
          f"({counts.get('parse_errors', 0)} parse errors)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
