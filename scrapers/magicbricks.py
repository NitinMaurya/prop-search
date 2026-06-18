"""MagicBricks fetcher + parser (D13). Selectors TUNED against live HTML 2026-06-18.

Unlike 99acres (Akamai-blocked from datacenter IPs, D16), MagicBricks served a real
1.4MB Noida SRP from the dev environment, so these selectors are verified, not guessed.

Fetcher: hardened Playwright (persistent profile + homepage warm-up + stealth, same as
  the 99acres fetcher) against the seeded SRP URL.
Parser:  div.mb-srp__card cards. Per card:
  - title  : h2.mb-srp__card--title::text   (e.g. "7 BHK House ... Sector 40 ... Noida")
  - price  : .mb-srp__card__price--amount::text   (e.g. "7 Cr")
  - area   : summary label/value list — prefer Plot/Super/Carpet Area (e.g. "3346 sqft")
  - sector : parsed out of the title
  - url    : the per-card detail URL is NOT on an <a> (JS click), but all 30 detail URLs
             are embedded in the page in card order — extracted via regex and zipped.
  - id     : card element id "propertiesAction<digits>"

Reuses normalize_price / normalize_size / _extract_sector from the 99acres plugin (DRY).
name = "MagicBricks"  # must match portals.name
"""

import logging
import re

from property_types import search_url as _category_search_url

# Reuse the tuned normalization helpers + the optional-lib guards (D14).
from scrapers.nineacres import (
    _HAVE_PARSEL, _HAVE_PLAYWRIGHT, Selector, sync_playwright,
    normalize_price, normalize_size, _extract_sector,
    HEADLESS, PROFILE_DIR as _ACRES_PROFILE, USER_AGENT, VIEWPORT,
    WAIT_TIMEOUT_MS, WARMUP_PAUSE_MS, _looks_blocked,
)

log = logging.getLogger(__name__)

HOMEPAGE = "https://www.magicbricks.com/"
PROFILE_DIR = _ACRES_PROFILE.replace("99acres", "magicbricks")

SELECTORS = {
    "result_ready": "div.mb-srp__card",
    "card": "div.mb-srp__card",
    "title": "h2.mb-srp__card--title::text",
    "price": ".mb-srp__card__price--amount::text",
    "summary_label": ".mb-srp__card__summary--label::text",
    "summary_value": ".mb-srp__card__summary--value::text",
}
# Area preference: match on SUPER BUILT-UP area for an independent house (user, D18).
# Fall back to built-up, then carpet, then plot if super area isn't listed.
AREA_LABEL_PRIORITY = ("Super Area", "Built Up Area", "Carpet Area", "Plot Area")
# Per-card detail URLs are embedded in the page (no <a> on cards). Card order matches.
_DETAIL_URL_RE = re.compile(r"https://www\.magicbricks\.com/propertyDetails/[^\"\\ ]{5,160}")


class Fetcher:
    """Hardened Playwright fetcher for MagicBricks (D13). Never raises; returns [] on block."""

    name = "MagicBricks"

    def fetch(self, requirement: dict, portal_cfg: dict) -> list[dict]:
        if not _HAVE_PLAYWRIGHT:
            log.warning("playwright not installed; MagicBricks fetch skipped")
            return []
        # Target the SRP for the requirement's category (D19: house/plot/apartment ->
        # the right proptype tokens). Fall back to the seeded portal template.
        url = (_category_search_url("magicbricks", requirement.get("property_type"))
               or portal_cfg.get("search_url_template") or HOMEPAGE)
        log.info("MagicBricks fetch: category=%r url=%s",
                 requirement.get("property_type"), url)
        try:
            from playwright_stealth import Stealth  # type: ignore
            pw_ctx = Stealth().use_sync(sync_playwright())
        except Exception:  # noqa: BLE001
            pw_ctx = sync_playwright()  # type: ignore[misc]

        import os
        try:
            with pw_ctx as p:  # type: ignore[misc]
                os.makedirs(PROFILE_DIR, exist_ok=True)
                context = p.chromium.launch_persistent_context(
                    PROFILE_DIR, headless=HEADLESS, user_agent=USER_AGENT,
                    viewport=VIEWPORT, locale="en-IN",
                    args=["--disable-blink-features=AutomationControlled"],
                    extra_http_headers={
                        "Accept-Language": "en-IN,en;q=0.9",
                        "Accept": ("text/html,application/xhtml+xml,application/xml;"
                                   "q=0.9,image/webp,*/*;q=0.8"),
                    },
                )
                try:
                    page = context.new_page()
                    try:
                        page.goto(HOMEPAGE, wait_until="domcontentloaded",
                                  timeout=WAIT_TIMEOUT_MS)
                        page.wait_for_timeout(WARMUP_PAUSE_MS)
                    except Exception as e:  # noqa: BLE001
                        log.debug("MagicBricks warmup failed (continuing): %s", e)
                    page.goto(url, wait_until="domcontentloaded", timeout=WAIT_TIMEOUT_MS)
                    try:
                        page.wait_for_selector(SELECTORS["result_ready"],
                                               timeout=WAIT_TIMEOUT_MS)
                    except Exception as e:  # noqa: BLE001
                        log.warning("MagicBricks: cards not found at %s: %s", url, e)
                    page.wait_for_timeout(2000)  # let lazy cards settle
                    html = page.content()
                    final_url = page.url
                finally:
                    context.close()
        except Exception as e:  # noqa: BLE001 - never raise (D13)
            log.error("MagicBricks fetch failed for %s: %s", url, e)
            return []

        if _looks_blocked(html):
            log.warning("MagicBricks returned a block/empty page (%d bytes)",
                        len(html or ""))
            return []
        return [{"url": final_url, "raw_html": html}]


class Parser:
    """parsel parser for MagicBricks (D13). One SRP page -> many listings. Never raises."""

    name = "MagicBricks"

    def parse(self, raw: dict) -> list[dict]:
        if not _HAVE_PARSEL:
            log.warning("parsel not installed; MagicBricks parse skipped")
            return []
        html = (raw or {}).get("raw_html")
        if not html:
            return []
        page_url = (raw or {}).get("url") or HOMEPAGE
        try:
            sel = Selector(text=html)
        except Exception as e:  # noqa: BLE001
            log.error("MagicBricks: failed to build selector: %s", e)
            return []

        # Detail URLs are embedded in page order; zip them to cards by index.
        detail_urls = _DETAIL_URL_RE.findall(html)
        cards = sel.css(SELECTORS["card"])
        listings: list[dict] = []
        for i, card in enumerate(cards):
            try:
                url = detail_urls[i] if i < len(detail_urls) else page_url
                listing = self._parse_one(card, url)
            except Exception as e:  # noqa: BLE001 - one bad card never aborts
                log.warning("MagicBricks: skipping bad card: %s", e)
                continue
            if listing is not None:
                listings.append(listing)
        if not listings:
            log.warning("MagicBricks: 0 listings parsed (selectors may be stale)")
        return listings

    def _parse_one(self, card, url: str) -> dict | None:
        title = _first(card.css(SELECTORS["title"]).getall())
        price = normalize_price(_first(card.css(SELECTORS["price"]).getall()))

        labels = [x.strip() for x in card.css(SELECTORS["summary_label"]).getall()]
        values = [x.strip() for x in card.css(SELECTORS["summary_value"]).getall()]
        summary = dict(zip(labels, values))
        area_text = next((summary[k] for k in AREA_LABEL_PRIORITY if k in summary), None)
        size_sqm = normalize_size(area_text)

        if price is None or size_sqm is None:
            log.info("MagicBricks: skipping card missing price/size (price=%r area=%r)",
                     price, area_text)
            return None

        cid = card.css("::attr(id)").get() or ""
        external_id = re.sub(r"\D", "", cid) or None
        return {
            "external_id": external_id,
            "url": url,
            "title": (title or "").strip() or None,
            "price": price,
            "size_sqm": size_sqm,
            "sector": _extract_sector(title),
            "raw_location": (title or "").strip() or None,  # MB folds location into title
            "posted_date": None,
        }


def _first(values):
    if not values:
        return None
    for v in values:
        if v and v.strip():
            return v.strip()
    return None


# Self-register with the loader (D13).
try:
    from scrapers.base import register
    register("MagicBricks", Fetcher, Parser)
except Exception:  # noqa: BLE001
    pass
