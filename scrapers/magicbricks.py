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

import json
import logging
import os
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
MAX_PAGES = 5  # result pages to walk per refresh (D25); ~30 listings each

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

# The SRP HTML embeds the full listing JSON (D23): each listing object carries images
# (allImgPath), approving authority (appovedAuthC), ownership (OwnershipTypeD), covered
# area, etc. We parse those straight out of the page — no API call or login needed.
# covAreaUnit code -> factor to convert the covered area to sqm (D18 = covered/built-up).
_UNIT_TO_SQM = {"12801": 1.0, "12800": 0.09290304, "12803": 0.83612736}


class Fetcher:
    """Hardened Playwright fetcher for MagicBricks (D13). Never raises; returns [] on block."""

    name = "MagicBricks"

    def fetch(self, requirement: dict, portal_cfg: dict) -> list[dict]:
        """Fetch via the persistent (possibly logged-in) browser profile (D22). Tries the
        SRP HTML — the full listing data (images, authority, ownership) is embedded in
        it (D23), so no API call / login is needed. Never raises; [] on block/error."""
        if not _HAVE_PLAYWRIGHT:
            log.warning("playwright not installed; MagicBricks fetch skipped")
            return []
        # SRP page for the requirement's category (D19).
        srp_url = (_category_search_url("magicbricks", requirement.get("property_type"))
                   or portal_cfg.get("search_url_template") or HOMEPAGE)
        log.info("MagicBricks fetch: category=%r", requirement.get("property_type"))
        try:
            from playwright_stealth import Stealth  # type: ignore
            pw_ctx = Stealth().use_sync(sync_playwright())
        except Exception:  # noqa: BLE001
            pw_ctx = sync_playwright()  # type: ignore[misc]

        rows: list[dict] = []
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
                    try:  # warm up + carry the logged-in session/Akamai cookies
                        page.goto(HOMEPAGE, wait_until="domcontentloaded",
                                  timeout=WAIT_TIMEOUT_MS)
                        page.wait_for_timeout(WARMUP_PAUSE_MS)
                    except Exception as e:  # noqa: BLE001
                        log.debug("MagicBricks warmup failed (continuing): %s", e)

                    # Walk result pages (D25): one raw row per page; the parser pulls the
                    # embedded listings from each. Stop on a blocked/empty/last page.
                    for pg_num in range(1, MAX_PAGES + 1):
                        page_url = srp_url + ("&" if "?" in srp_url else "?") + \
                            f"page={pg_num}"
                        try:
                            page.goto(page_url, wait_until="domcontentloaded",
                                      timeout=WAIT_TIMEOUT_MS)
                            page.wait_for_timeout(1800)  # let listings settle
                            html = page.content()
                        except Exception as e:  # noqa: BLE001
                            log.warning("MagicBricks page %d failed: %s", pg_num, e)
                            break
                        # Real SRP pages are >500KB; a few-KB page is an Akamai
                        # challenge/interstitial, not a genuine empty results page.
                        if _looks_blocked(html) or len(html) < 50000:
                            log.warning("MagicBricks page %d blocked/challenge (%d bytes)",
                                        pg_num, len(html or ""))
                            break
                        has_listings = '"encId":"' in html
                        if has_listings or pg_num == 1:
                            rows.append({"url": page_url, "raw_html": html})
                            log.info("MagicBricks page %d fetched (%d bytes, listings=%s)",
                                     pg_num, len(html), has_listings)
                        if not has_listings:  # past the last page
                            break
                finally:
                    context.close()
        except Exception as e:  # noqa: BLE001 - never raise (D13)
            log.error("MagicBricks fetch failed: %s", e)
            return rows

        if not rows:
            log.warning("MagicBricks returned no usable pages")
        return rows

class Parser:
    """parsel parser for MagicBricks (D13). One SRP page -> many listings. Never raises."""

    name = "MagicBricks"

    def parse(self, raw: dict) -> list[dict]:
        html = (raw or {}).get("raw_html")
        if not html:
            return []
        # JSON API response (D20) — detect and parse without parsel.
        if html.lstrip().startswith("{"):
            return self._parse_json(html)
        # SRP HTML: the listings are embedded as JSON objects (D23) carrying images +
        # authority + ownership. Extract those first; fall back to card scraping.
        embedded = self._parse_embedded(html)
        if embedded:
            log.info("MagicBricks: %d listings from embedded JSON", len(embedded))
            return embedded
        log.info("MagicBricks: no embedded JSON; scraping HTML cards")
        if not _HAVE_PARSEL:
            log.warning("parsel not installed; MagicBricks parse skipped")
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


    # ----------------------------------------------- embedded SRP JSON parsing (D23)
    def _parse_embedded(self, html: str) -> list[dict]:
        """Extract per-listing objects embedded in the SRP HTML. Each listing object
        begins with `"encId":"`, so we split on that and regex the fields we need from
        each chunk (robust to the page's overall structure)."""
        chunks = html.split('"encId":"')
        if len(chunks) < 2:
            return []
        out, seen = [], set()
        for ch in chunks[1:]:
            try:
                lst = self._parse_embedded_one(ch[:9000])
            except Exception as e:  # noqa: BLE001 - one bad chunk never aborts
                log.debug("MagicBricks: bad embedded chunk: %s", e)
                continue
            if lst and lst["external_id"] not in seen:
                seen.add(lst["external_id"])
                out.append(lst)
        return out

    def _parse_embedded_one(self, ch: str) -> dict | None:
        price = _emb(ch, "price", num=True)
        size = _json_area_to_sqm(_emb(ch, "coveredArea") or _emb(ch, "ca"),
                                 str(_emb(ch, "covAreaUnit") or ""))
        ext_id = _emb(ch, "id")
        if not price or size is None or not ext_id:
            return None
        u = _emb(ch, "url")
        url = ("https://www.magicbricks.com/propertyDetails/" + u) if u else HOMEPAGE
        name = (_emb(ch, "companyname") or _emb(ch, "oname")
                or _emb(ch, "contName") or "")
        advertiser = " · ".join(x for x in (name, _emb(ch, "userType")) if x) or None
        image = _emb(ch, "allImgPath_first") or _emb(ch, "image")
        return {
            "external_id": str(ext_id),
            "url": url,
            "title": _emb(ch, "propertyTitle") or _emb(ch, "auto_desc"),
            "price": int(price),
            "size_sqm": size,
            "sector": _emb(ch, "lmtDName") or _emb(ch, "locSeoName"),
            "raw_location": _emb(ch, "lmtDName"),
            "posted_date": _emb(ch, "postDateT"),
            "image_url": image,
            "advertiser": advertiser,
            "ownership": _emb(ch, "OwnershipTypeD"),
            "approving_authority": _emb(ch, "appovedAuthC"),
        }

    # ---------------------------------------------------------------- JSON parsing (D20)
    def _parse_json(self, body: str) -> list[dict]:
        try:
            data = json.loads(body)
        except Exception as e:  # noqa: BLE001
            log.error("MagicBricks: bad JSON: %s", e)
            return []
        items = (data.get("nsrResultList") or []) + (data.get("resultList") or [])
        listings, seen = [], set()
        for item in items:
            try:
                lst = self._parse_json_one(item)
            except Exception as e:  # noqa: BLE001 - one bad item never aborts
                log.warning("MagicBricks: skipping bad JSON item: %s", e)
                continue
            if lst and lst["external_id"] not in seen:
                seen.add(lst["external_id"])
                listings.append(lst)
        if not listings:
            log.warning("MagicBricks JSON: 0 listings parsed")
        return listings

    def _parse_json_one(self, item: dict) -> dict | None:
        price = item.get("price")
        area = item.get("coveredArea") or item.get("ca")
        size_sqm = _json_area_to_sqm(area, str(item.get("covAreaUnit") or ""))
        if not price or size_sqm is None:
            return None
        u = item.get("url")
        url = ("https://www.magicbricks.com/propertyDetails/" + u) if u else HOMEPAGE
        name = (item.get("companyname") or item.get("oname")
                or item.get("contName") or "").strip()
        advertiser = " · ".join(x for x in (name, item.get("userType")) if x) or None
        images = item.get("allImgPath") or []
        image_url = item.get("image") or (images[0] if images else None)
        return {
            "external_id": str(item.get("id")) if item.get("id") else None,
            "url": url,
            "title": (item.get("propertyTitle") or item.get("auto_desc") or "").strip()
                     or None,
            "price": int(price),
            "size_sqm": size_sqm,
            "sector": (item.get("lmtDName") or item.get("locSeoName") or "").strip()
                      or None,
            "raw_location": (item.get("lmtDName") or "").strip() or None,
            "posted_date": item.get("postDateT"),
            "image_url": image_url,
            "advertiser": advertiser,
            "ownership": (item.get("OwnershipTypeD") or "").strip() or None,
            "approving_authority": (item.get("appovedAuthC") or "").strip() or None,
        }


def _emb_unescape(v: str):
    """Unescape a JSON string value pulled out of embedded HTML (\\u002F -> / etc.)."""
    try:
        return json.loads('"' + v + '"')
    except Exception:  # noqa: BLE001
        return v


def _emb(chunk: str, key: str, num: bool = False):
    """Regex one field out of a single embedded-listing chunk (D23)."""
    if key == "allImgPath_first":
        m = re.search(r'"allImgPath":\["((?:[^"\\]|\\.)*)"', chunk)
        return _emb_unescape(m.group(1)) if m else None
    pat = r'"' + re.escape(key) + r'":' + (r"(\d+)" if num else r'"((?:[^"\\]|\\.)*)"')
    m = re.search(pat, chunk)
    if not m:
        return None
    if num:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return _emb_unescape(m.group(1)) or None


def _json_area_to_sqm(area, unit_code: str):
    """Convert a JSON covered-area value (+ covAreaUnit code) to sqm (D18/D20)."""
    if area is None or area == "":
        return None
    try:
        val = float(str(area).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if val <= 0:
        return None
    return round(val * _UNIT_TO_SQM.get(unit_code, 1.0), 2)


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
