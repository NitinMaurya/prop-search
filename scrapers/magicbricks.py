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
import re

from property_types import search_url as _category_search_url

# Reuse the tuned normalization helpers + the optional-lib guards (D14).
from scrapers.nineacres import (
    _HAVE_PARSEL, _HAVE_PLAYWRIGHT, Selector,
    normalize_price, normalize_size, size_from_description, _extract_sector,
    PROFILE_DIR as _ACRES_PROFILE,
    WAIT_TIMEOUT_MS, WARMUP_PAUSE_MS, _looks_blocked,
    pw_session, launch_stealth_context,
)

log = logging.getLogger(__name__)

HOMEPAGE = "https://www.magicbricks.com/"
PROFILE_DIR = _ACRES_PROFILE.replace("99acres", "magicbricks")
# Budget is filtered SERVER-SIDE via the URL (D27): MagicBricks honours BudgetMin/BudgetMax
# (in rupees) on the SRP, so every returned listing is already in-budget. That shrinks the
# result set enough to walk it to exhaustion — we paginate until a page has no listings,
# with MAX_PAGES only as a safety backstop (sort params like sortBy=priceasc are ignored).
MAX_PAGES = 20  # safety cap; the real stop is "EMPTY_STREAK consecutive empty pages"
EMPTY_STREAK = 2     # stop after this many consecutive empty pages (genuine end of results)
PAGE_ATTEMPTS = 3    # retries per page before giving up on it (throttle stubs are transient)
PAGE_SETTLE_MS = 2200    # let embedded listings render after navigation
PAGE_BACKOFF_MS = 3500   # base backoff between retries (multiplied by attempt #)
MIN_REAL_PAGE_BYTES = 50000  # smaller than this = throttle stub / challenge, not real SRP


def _with_budget(url: str, requirement: dict) -> str:
    """Append MagicBricks BudgetMin/BudgetMax (rupees) from the requirement (D27).
    Server-side budget filter, so pagination only walks in-budget inventory.

    BudgetMax MUST be paired with BudgetMin or MagicBricks returns an 8 KB empty stub /
    redirect loop (verified live) — so we always emit BudgetMin (default 0) alongside it.
    """
    bmax = requirement.get("budget_max")
    if not bmax:
        return url  # no ceiling -> unfiltered city-wide search (matcher still filters)
    bmin = int(requirement.get("budget_min") or 0)
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}BudgetMin={bmin}&BudgetMax={int(bmax)}"


def _with_locality(url: str, sector: str) -> str:
    """Scope an SRP to a single Noida sector via MagicBricks' `Locality=Sector-N`
    filter (D28, confirmed live). A city-wide budget search caps at ~90 listings, but
    one search per sector surfaces that sector's full inventory (~30-36/sector)."""
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}Locality=Sector-{sector}"


def _page_url(url: str, n: int) -> str:
    """URL for result page n (D27). Page 1 is the bare URL. For pages 2+ the `page=N`
    param MUST precede the budget params — appended at the END, MagicBricks returns an
    empty 8 KB stub; placed right after `?` it paginates correctly (verified live)."""
    if n <= 1:
        return url
    if "?" in url:
        path, query = url.split("?", 1)
        return f"{path}?page={n}&{query}"
    return f"{url}?page={n}"

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
# Per-listing id in the embedded JSON — used in the fetch loop to detect when MagicBricks
# starts repeating the last page (out-of-range pages echo it), i.e. the real end (D27).
_ENCID_RE = re.compile(r'"encId":"([^"]{4,40})')

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
        # SRP page for the requirement's category (D19) + server-side budget filter (D27).
        cat_url = (_category_search_url("magicbricks", requirement.get("property_type"))
                   or portal_cfg.get("search_url_template") or HOMEPAGE)
        # One budget-filtered search PER SECTOR (D28) — far more inventory than the
        # ~90-listing cap of a single city-wide search. No sectors -> one city-wide search.
        sectors = [str(s).strip() for s in (requirement.get("sectors") or []) if str(s).strip()]
        searches = ([(s, _with_budget(_with_locality(cat_url, s), requirement)) for s in sectors]
                    if sectors else [(None, _with_budget(cat_url, requirement))])
        log.info("MagicBricks fetch: category=%r budget=%s-%s sectors=%s",
                 requirement.get("property_type"),
                 requirement.get("budget_min"), requirement.get("budget_max"),
                 sectors or "all")

        rows: list[dict] = []
        try:
            with pw_session() as p:  # type: ignore[misc]
                context = launch_stealth_context(p, PROFILE_DIR)
                try:
                    page = context.new_page()
                    try:  # warm up + carry the logged-in session/Akamai cookies
                        page.goto(HOMEPAGE, wait_until="domcontentloaded",
                                  timeout=WAIT_TIMEOUT_MS)
                        page.wait_for_timeout(WARMUP_PAUSE_MS)
                    except Exception as e:  # noqa: BLE001
                        log.debug("MagicBricks warmup failed (continuing): %s", e)

                    # Walk each search to exhaustion. seen_ids is shared across sectors so
                    # a listing surfacing in two sector searches is only stored once.
                    seen_ids: set[str] = set()
                    for sector, srp_url in searches:
                        self._walk_pages(page, srp_url, sector, seen_ids, rows)
                finally:
                    context.close()
        except Exception as e:  # noqa: BLE001 - never raise (D13)
            log.error("MagicBricks fetch failed: %s", e)
            return rows

        if not rows:
            log.warning("MagicBricks returned no usable pages")
        return rows

    def _walk_pages(self, page, srp_url: str, sector, seen_ids: set, rows: list) -> None:
        """Paginate one budget-filtered search to exhaustion, appending a raw row per
        page with new listings (D27/D28). MagicBricks intermittently serves an 8 KB
        throttle stub for a valid page, so _get_page retries with backoff; we stop after
        EMPTY_STREAK consecutive empties (genuine end) or when a page adds no new listings
        (out-of-range pages echo the last one). Found IDs accumulate in the shared seen_ids
        so the same listing is never stored twice across sectors."""
        tag = f"sector {sector}" if sector else "city-wide"
        empty_streak = 0
        for pg_num in range(1, MAX_PAGES + 1):
            html = self._get_page(page, _page_url(srp_url, pg_num), pg_num)
            if not (html and '"encId":"' in html):
                empty_streak += 1
                log.info("MagicBricks %s page %d empty (streak %d/%d)",
                         tag, pg_num, empty_streak, EMPTY_STREAK)
                if empty_streak >= EMPTY_STREAK:
                    break
                continue
            empty_streak = 0
            new_ids = set(_ENCID_RE.findall(html)) - seen_ids
            if not new_ids:  # out-of-range page echoing the last one -> end of this search
                log.info("MagicBricks %s page %d has no new listings; stopping", tag, pg_num)
                break
            seen_ids |= new_ids
            rows.append({"url": _page_url(srp_url, pg_num), "raw_html": html})
            log.info("MagicBricks %s page %d fetched (%d bytes, %d new)",
                     tag, pg_num, len(html), len(new_ids))

    def _get_page(self, page, url: str, pg_num: int) -> str | None:
        """Navigate to one result page, retrying past transient throttle stubs / redirect
        loops with backoff (D27). Returns the HTML of a real SRP, or None if every attempt
        came back as a stub / block / nav error (treated as an empty page by the caller)."""
        for attempt in range(1, PAGE_ATTEMPTS + 1):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=WAIT_TIMEOUT_MS)
                page.wait_for_timeout(PAGE_SETTLE_MS)
                html = page.content()
            except Exception as e:  # noqa: BLE001 - redirect loop / timeout is retryable
                log.warning("MagicBricks page %d attempt %d nav error: %s",
                            pg_num, attempt, str(e).splitlines()[0])
                page.wait_for_timeout(PAGE_BACKOFF_MS * attempt)
                continue
            # A real SRP is hundreds of KB; a few-KB page is a throttle stub / challenge.
            if _looks_blocked(html) or len(html) < MIN_REAL_PAGE_BYTES:
                log.warning("MagicBricks page %d attempt %d throttle stub (%d bytes); "
                            "backing off", pg_num, attempt, len(html or ""))
                page.wait_for_timeout(PAGE_BACKOFF_MS * attempt)
                continue
            return html
        return None


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
        ext_id = _emb(ch, "id")
        desc = _clean_desc(_emb(ch, "plgdtldesc") or _emb(ch, "dtldesc")
                           or _emb(ch, "ampDesc"))
        # Prefer an explicit plot/area size stated in the description; fall back to the
        # portal's covered-area figure (D31).
        size = size_from_description(desc) or _json_area_to_sqm(
            _emb(ch, "coveredArea") or _emb(ch, "ca"), str(_emb(ch, "covAreaUnit") or ""))
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
            "description": desc,
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
        desc = _clean_desc(item.get("plgdtldesc") or item.get("dtldesc")
                           or item.get("ampDesc"))
        # Prefer an explicit plot/area size from the description; card area is fallback (D31).
        area = item.get("coveredArea") or item.get("ca")
        size_sqm = (size_from_description(desc)
                    or _json_area_to_sqm(area, str(item.get("covAreaUnit") or "")))
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
            "description": desc,
        }


def _clean_desc(s):
    """Tidy an owner-written description (D30): strip HTML tags (<br> etc.), collapse
    whitespace, cap length. Returns None if empty."""
    if not s:
        return None
    s = re.sub(r"<[^>]+>", " ", str(s))      # drop any HTML tags
    s = re.sub(r"\s+", " ", s).strip()
    return s[:800] or None


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
