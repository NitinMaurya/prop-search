"""Housing.com fetcher + parser (D13). SKELETON — selectors NOT yet tuned (D16).

Housing.com blocked this datacenter-IP dev environment with a "Security Alert / Request
Blocked" page (D16), so its real card HTML couldn't be inspected. The fetcher is the
same hardened approach as MagicBricks; the parser SELECTORS are placeholders that MUST
be tuned against a real SRP fetched from a residential IP (see SCRAPER_GUIDE).

Housing.com is a React SPA: listings are rendered client-side and the page also embeds
JSON. When tuning, check both the rendered cards AND any embedded JSON for cleaner data.
Follow D18: size = SUPER BUILT-UP area (prefer super/built-up over carpet).

name = "Housing.com"   # must match portals.name
"""

import logging
import re

from scrapers.nineacres import (
    _HAVE_PARSEL, _HAVE_PLAYWRIGHT, Selector,
    normalize_price, normalize_size, _extract_sector,
    PROFILE_DIR as _ACRES_PROFILE,
    WAIT_TIMEOUT_MS, WARMUP_PAUSE_MS, _looks_blocked,
    pw_session, launch_stealth_context,
)

log = logging.getLogger(__name__)

HOMEPAGE = "https://housing.com/"
PROFILE_DIR = _ACRES_PROFILE.replace("99acres", "housing")

# TODO: tune against a live Housing.com SRP fetched from a residential IP (D16). These
# are PLACEHOLDER guesses — Housing.com uses obfuscated/generated class names that change.
SELECTORS = {
    "result_ready": "[data-testid='srp-tuple'], article, div[class*='card']",
    "card": "[data-testid='srp-tuple'], article",
    "title": "h2 a::text, h2::text",
    "url": "h2 a::attr(href), a::attr(href)",
    "price": "[class*='price']::text",
    "area": "[class*='area']::text",
    "location": "[class*='locality']::text, [class*='location']::text",
}
# Housing.com area labels for the D18 super-built-up preference, when present.
AREA_LABEL_PRIORITY = ("Super Area", "Built Up Area", "Carpet Area", "Plot Area")
BASE_URL = "https://housing.com"


class Fetcher:
    """Hardened Playwright fetcher for Housing.com (D13). Never raises; [] on block."""

    name = "Housing.com"

    def fetch(self, requirement: dict, portal_cfg: dict) -> list[dict]:
        if not _HAVE_PLAYWRIGHT:
            log.warning("playwright not installed; Housing.com fetch skipped")
            return []
        url = portal_cfg.get("search_url_template") or HOMEPAGE
        try:
            with pw_session() as p:  # type: ignore[misc]
                context = launch_stealth_context(p, PROFILE_DIR)
                try:
                    page = context.new_page()
                    try:
                        page.goto(HOMEPAGE, wait_until="domcontentloaded",
                                  timeout=WAIT_TIMEOUT_MS)
                        page.wait_for_timeout(WARMUP_PAUSE_MS)
                    except Exception as e:  # noqa: BLE001
                        log.debug("Housing.com warmup failed (continuing): %s", e)
                    page.goto(url, wait_until="domcontentloaded", timeout=WAIT_TIMEOUT_MS)
                    try:
                        page.wait_for_selector(SELECTORS["result_ready"],
                                               timeout=WAIT_TIMEOUT_MS)
                    except Exception as e:  # noqa: BLE001
                        log.warning("Housing.com: cards not found at %s: %s", url, e)
                    page.wait_for_timeout(2000)
                    html = page.content()
                    final_url = page.url
                finally:
                    context.close()
        except Exception as e:  # noqa: BLE001 - never raise (D13)
            log.error("Housing.com fetch failed for %s: %s", url, e)
            return []

        if _looks_blocked(html):
            log.warning("Housing.com returned a block/empty page (%d bytes) — tune on a "
                        "residential IP (D16)", len(html or ""))
            return []
        return [{"url": final_url, "raw_html": html}]


class Parser:
    """parsel parser for Housing.com (D13). SKELETON — verify selectors before trusting.
    One SRP page -> many listings. Never raises on a single bad card."""

    name = "Housing.com"

    def parse(self, raw: dict) -> list[dict]:
        if not _HAVE_PARSEL:
            log.warning("parsel not installed; Housing.com parse skipped")
            return []
        html = (raw or {}).get("raw_html")
        if not html:
            return []
        page_url = (raw or {}).get("url") or HOMEPAGE
        try:
            sel = Selector(text=html)
        except Exception as e:  # noqa: BLE001
            log.error("Housing.com: failed to build selector: %s", e)
            return []

        listings: list[dict] = []
        for card in sel.css(SELECTORS["card"]):
            try:
                listing = self._parse_one(card, page_url)
            except Exception as e:  # noqa: BLE001 - one bad card never aborts
                log.warning("Housing.com: skipping bad card: %s", e)
                continue
            if listing is not None:
                listings.append(listing)
        if not listings:
            log.warning("Housing.com: 0 listings parsed (SKELETON selectors likely need "
                        "tuning on a residential IP — D16)")
        return listings

    def _parse_one(self, card, page_url: str) -> dict | None:
        title = _first(card.css(SELECTORS["title"]).getall())
        price = normalize_price(_first(card.css(SELECTORS["price"]).getall()))
        size_sqm = normalize_size(_first(card.css(SELECTORS["area"]).getall()))
        location = _first(card.css(SELECTORS["location"]).getall())
        href = _first(card.css(SELECTORS["url"]).getall())
        if price is None or size_sqm is None:
            return None
        url = href if (href or "").startswith("http") else BASE_URL + (href or "")
        return {
            "external_id": None,
            "url": url or page_url,
            "title": (title or "").strip() or None,
            "price": price,
            "size_sqm": size_sqm,
            "sector": _extract_sector(location or title),
            "raw_location": (location or "").strip() or None,
            "posted_date": None,
        }


def _first(values):
    if not values:
        return None
    for v in values:
        if v and v.strip():
            return v.strip()
    return None


try:
    from scrapers.base import register
    register("Housing.com", Fetcher, Parser)
except Exception:  # noqa: BLE001
    pass
