"""99acres fetcher + parser (build step 3 — first portal, riskiest piece).

Implements scrapers/base.py Fetcher + Parser (D13). Decoupled via raw_listings (D12).

Fetcher: build search URL (map "kothi" -> Independent House / Villa, D8), drive
  Playwright + playwright-stealth, wait for result-card selectors, return {url, raw_html}.
Parser: parsel/bs4 selectors -> fields; price-parser for "Rs 4.25 Cr"; convert size to
  sqm (sqft*0.092903, sqyd*0.836127). See docs/SCRAPER_GUIDE.md. Parse defensively.

name = "99acres"   # must match portals.name

NOTE ON LIBRARIES (D14): playwright / playwright-stealth / parsel / price-parser are
optional at import time. They are guarded so this module imports cleanly before
`pip install` — fetch() degrades to returning [] with a log line, and the price/size
normalization helpers are pure-Python and always testable offline (see __main__).
"""

import logging
import re

log = logging.getLogger(__name__)

# --------------------------------------------------------------- optional library guards
# Guarded so `import scrapers.nineacres` never crashes when libs are absent (D14).
# Prefer Patchright (D26): a drop-in Playwright replacement that patches the automation
# fingerprints Akamai/Cloudflare detect. Its sync API is 1:1 with Playwright's, so the
# rest of the code is unchanged. Fall back to vanilla Playwright if Patchright is absent.
try:
    from patchright.sync_api import sync_playwright  # type: ignore
    _HAVE_PLAYWRIGHT = True
    _USING_PATCHRIGHT = True
except ImportError:  # pragma: no cover - depends on environment
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
        _HAVE_PLAYWRIGHT = True
    except ImportError:
        sync_playwright = None  # type: ignore
        _HAVE_PLAYWRIGHT = False
    _USING_PATCHRIGHT = False

try:
    # playwright-stealth API has shifted across versions; accept either entrypoint.
    try:
        from playwright_stealth import stealth_sync  # type: ignore
    except ImportError:  # pragma: no cover
        from playwright_stealth import Stealth  # type: ignore

        def stealth_sync(page):  # type: ignore
            Stealth().apply_stealth_sync(page)
    _HAVE_STEALTH = True
except ImportError:  # pragma: no cover
    stealth_sync = None  # type: ignore
    _HAVE_STEALTH = False

try:
    from parsel import Selector  # type: ignore
    _HAVE_PARSEL = True
except ImportError:  # pragma: no cover
    Selector = None  # type: ignore
    _HAVE_PARSEL = False

try:
    from price_parser import Price  # type: ignore
    _HAVE_PRICE_PARSER = True
except ImportError:  # pragma: no cover
    Price = None  # type: ignore
    _HAVE_PRICE_PARSER = False


# ============================================================== SELECTOR / URL CONSTANTS
# TODO: tune against live 99acres HTML. 99acres renders result cards client-side and
# changes class names / data-attrs frequently. Every selector below is a PLACEHOLDER
# educated guess and WILL need verification against a real fetched page (the irreducible
# per-site work, D14). Re-inspect when a run returns 0 cards (SCRAPER_GUIDE rule of thumb).
SELECTORS = {
    # Container the fetcher waits for before capturing HTML (presence = results loaded).
    "result_ready": "div.srpTuple__tupleDetails, [data-label='SRP_TUPLE']",
    # One element per listing card; parse() iterates these.
    "card": "div.srpTuple__tupleDetails, [data-label='SRP_TUPLE']",
    # Fields relative to a card.
    "title": "h2 a::text, a.srpTuple__propertyName::text",
    "url": "h2 a::attr(href), a.srpTuple__propertyName::attr(href)",
    "price": "div.srpTuple__price::text, span.srpTuple__spacer10::text",
    "size": "div.srpTuple__area::text, td.srpTuple__area::text",
    "location": "div.srpTuple__locName::text, span.srpTuple__locName::text",
    "external_id": "::attr(data-id)",
    "posted_date": "div.srpTuple__postedOn::text",
}

# D8: "kothi" -> 99acres category. The seeded search_url_template already points at the
# independent-house/villa SRP; these are the property-type codes 99acres uses on its SRP
# query string for that segment. Kept here so the mapping lives in the plugin (D8).
KOTHI_PROPERTY_TYPES = "1,4,5"  # Independent House / Villa / Independent Floor (TODO: verify)

# Playwright settings — realistic UA + viewport, headful-like (SCRAPER_GUIDE).
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
VIEWPORT = {"width": 1366, "height": 900}
WAIT_TIMEOUT_MS = 25000

# Unit conversion factors -> square metres (SCRAPER_GUIDE).
SQFT_TO_SQM = 0.092903
SQYD_TO_SQM = 0.836127

# Crore / lakh multipliers (Indian number system). price-parser returns the numeric
# amount; we apply the multiplier detected from the surrounding text.
CRORE = 10_000_000   # 1e7
LAKH = 100_000       # 1e5


# ===================================================================== normalization
def normalize_price(text: str | None) -> int | None:
    """Parse an Indian price string to integer rupees, or None if unparseable.

    Handles "Rs 4.25 Cr", "4.5 Crore", "85 Lakh", and plain "4,25,00,000". Uses
    price-parser for the numeric amount when available, with a regex fallback so the
    helper still works (and is unit-testable) without the library installed.
    """
    if not text:
        return None
    t = str(text).strip()
    if not t:
        return None
    low = t.lower()

    # Detect the Indian-system multiplier from words/abbreviations in the text.
    if re.search(r"\bcr\b|crore", low):
        multiplier = CRORE
    elif re.search(r"\blac\b|\blakh\b|\blacs\b|\blakhs\b|\bl\b", low):
        multiplier = LAKH
    else:
        multiplier = 1

    amount = None
    if _HAVE_PRICE_PARSER:
        parsed = Price.fromstring(t)  # type: ignore[union-attr]
        if parsed.amount is not None:
            amount = float(parsed.amount)
    if amount is None:
        # Fallback: pull the first numeric token (keeps grouping commas / decimal point).
        m = re.search(r"[\d][\d,]*\.?\d*", t)
        if not m:
            return None
        num = m.group(0).replace(",", "")
        try:
            amount = float(num)
        except ValueError:
            return None

    rupees = int(round(amount * multiplier))
    return rupees if rupees > 0 else None


def normalize_size(text: str | None) -> float | None:
    """Parse an area string to square metres (float), or None if unparseable.

    Recognizes sq.ft / sqft / sq ft, sq.yd / sqyd / sq yard, and sq.m / sqm. Defaults
    to treating a bare number as sqft (the 99acres default unit). Returns sqm.
    """
    if not text:
        return None
    t = str(text).strip().lower()
    if not t:
        return None

    m = re.search(r"([\d][\d,]*\.?\d*)", t)
    if not m:
        return None
    try:
        value = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    if value <= 0:
        return None

    # Square YARD (gaj): match sq+yd/yrd/yard/yds variants and "gaj". The 'r' in "sqyrd"
    # and missing separators are common on Indian portals, so be liberal here.
    if re.search(r"sq\.?\s*y(?:d|rd|ard|ds|rds)?\b|sqyrd|\bgaj\b|\byards?\b", t):
        return round(value * SQYD_TO_SQM, 2)
    # Square METRE: sqm / sq.m / sq m / sq.mt / meter / metre.
    if re.search(r"sq\.?\s*m(?:t|tr|eter|etre)?\b|sqm|\bsq\.?\s*metre", t):
        return round(value, 2)
    # sq.ft / sqft / sq ft, or a bare number -> assume sqft (portal default).
    return round(value * SQFT_TO_SQM, 2)


# Area mentions inside free-text descriptions: a number directly followed by an explicit
# unit. Bare numbers in prose are NOT matched (too ambiguous). Bare "yards"/"meter" without
# "sq" are excluded too ("200 yards from metro", "5 meter road"); "gaj" is always area.
_DESC_AREA_RE = re.compile(
    r"(\d[\d,]*\.?\d*)\s*"
    r"(sq\.?\s*m(?:t|tr|eter|etre)?s?|sqm|sq\.?\s*metres?"          # square metre
    r"|sq\.?\s*y(?:d|rd|ard|ds|rds)?s?|sqyrds?|\bgaj\b"            # square yard / gaj
    r"|sq\.?\s*f(?:t|eet)?s?|sqft|sq\.?\s*feet)",                  # square foot
    re.IGNORECASE)
# Words just before an area number that flag it as the plot/total area we want (vs
# built-up/super/carpet, which we only fall back to when nothing better is quoted).
_PLOT_HINT = re.compile(r"(plot|land|area|size|dimension)\W*$", re.IGNORECASE)
_BUILT_HINT = re.compile(r"(built|super|carpet|covered|construct)\w*\W*$", re.IGNORECASE)


def size_from_description(text: str | None) -> float | None:
    """Best explicit plot/area size stated in a listing description, in sqm, or None.

    Preferred over the portal's card area (often a sqft super/built-up figure) when
    present; the card-derived size stays as the fallback. Requires an explicit unit.
    When several areas are quoted, a plot/land/area-labelled one wins over a
    built-up/super/carpet one.
    """
    if not text:
        return None
    best = None  # (score, sqm) — higher score wins; first match breaks ties
    for m in _DESC_AREA_RE.finditer(text):
        try:
            value = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if value <= 0:
            continue
        unit = m.group(2).lower()
        if "y" in unit or "gaj" in unit:
            sqm = value * SQYD_TO_SQM
        elif "m" in unit:
            sqm = value
        else:
            sqm = value * SQFT_TO_SQM
        before = text[:m.start()][-24:]
        score = (3 if _PLOT_HINT.search(before)
                 else 0 if _BUILT_HINT.search(before) else 1)
        if best is None or score > best[0]:
            best = (score, round(sqm, 2))
    return best[1] if best else None


def _extract_sector(location: str | None) -> str | None:
    """Pull a normalized 'Sector N' out of a raw location string, if present."""
    if not location:
        return None
    m = re.search(r"sector[\s-]*([0-9]+[a-z]?)", location, re.IGNORECASE)
    if m:
        return f"Sector {m.group(1).upper()}"
    return None


def _abs_url(href: str | None, base_url: str) -> str | None:
    if not href:
        return None
    href = href.strip()
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        return "https:" + href
    return base_url.rstrip("/") + "/" + href.lstrip("/")


def _build_search_url(requirement: dict, portal_cfg: dict) -> str:
    """Build the SRP URL from the portal template (D8 kothi mapping applied)."""
    template = portal_cfg.get("search_url_template", "")
    sectors = requirement.get("sectors") or []
    sizes = requirement.get("sizes_sqm") or []
    fields = {
        "sector": sectors[0] if sectors else "",
        "price_min": requirement.get("budget_min", ""),
        "price_max": requirement.get("budget_max", ""),
        "size": sizes[0] if sizes else "",
    }
    try:
        url = template.format(**fields)
    except (KeyError, IndexError, ValueError):
        # Template may have no placeholders (seeded SRP URL) — use it as-is.
        url = template
    return url


# --------------------------------------------------------------------- anti-bot tuning
# 99acres sits behind Akamai (D16). These are the levers that actually help — most of
# all a RESIDENTIAL IP (Akamai blocks datacenter IPs outright). Run headful on your own
# machine for the best results; HEADLESS can be overridden via env for debugging.
import os as _os

HOMEPAGE = "https://www.99acres.com/"
# Persistent profile so Akamai cookies (_abck / bm_sz) mature across runs — a fresh
# context every run looks like a brand-new bot each time and gets blocked harder.
PROFILE_DIR = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)),
                            "data", ".pw-99acres-profile")
# Default HEADFUL (D26): a visible real browser on a residential IP is what actually
# beats Akamai. Set PROP_HEADLESS=1 to run hidden (weaker; for debugging/servers only).
HEADLESS = _os.environ.get("PROP_HEADLESS", "0") == "1"
# Patchright works best driving real Chrome rather than bundled Chromium. Override via
# PROP_BROWSER_CHANNEL (e.g. "chrome-beta", "msedge"); empty -> bundled Chromium.
BROWSER_CHANNEL = _os.environ.get("PROP_BROWSER_CHANNEL", "chrome")
WARMUP_PAUSE_MS = 2500
BLOCK_MARKERS = ("Access Denied", "You don't have permission", "Request unsuccessful",
                 "captcha", "Pardon Our Interruption", "Request Blocked", "Security Alert",
                 "suspicious activity")


def _looks_blocked(html: str) -> bool:
    """Detect an Akamai/anti-bot block page vs. a real SRP (D16)."""
    if not html or len(html) < 1500:  # real SRP pages are tens-to-hundreds of KB
        return True
    return any(marker.lower() in html.lower() for marker in BLOCK_MARKERS)


# ------------------------------------------------- shared browser launch helpers (D26)
# All three portal fetchers drive the browser identically; the only per-portal differences
# are the URLs and selectors. Centralize the launch so Patchright's stealth rules live in
# one place and a fingerprint tweak applies to every portal at once.
def pw_session():
    """Return a Playwright/Patchright context manager for `with ... as p`.

    With vanilla Playwright we wrap the session in playwright-stealth. With Patchright we
    DON'T — Patchright is itself the stealth layer, and stacking playwright-stealth on top
    re-introduces detectable patches. Caller is responsible for `_HAVE_PLAYWRIGHT`.
    """
    if not _USING_PATCHRIGHT:
        try:
            from playwright_stealth import Stealth  # type: ignore
            return Stealth().use_sync(sync_playwright())
        except Exception:  # noqa: BLE001
            pass
    return sync_playwright()  # type: ignore[misc]


def launch_stealth_context(p, profile_dir: str):
    """Launch a persistent browser context tuned for anti-bot evasion (D26).

    Patchright path: drive real Chrome (channel) with NO custom user-agent / automation
    args — overriding those re-adds the very fingerprints Patchright strips. Falls back to
    bundled Chromium if the Chrome channel isn't installed. Vanilla-Playwright path keeps
    the old realistic-UA + AutomationControlled args (best it can do without Patchright).
    """
    _os.makedirs(profile_dir, exist_ok=True)
    base = dict(headless=HEADLESS, viewport=VIEWPORT, locale="en-IN")
    if _USING_PATCHRIGHT:
        opts = dict(base, channel=BROWSER_CHANNEL) if BROWSER_CHANNEL else dict(base)
    else:
        opts = dict(
            base,
            user_agent=USER_AGENT,
            args=["--disable-blink-features=AutomationControlled"],
            extra_http_headers={
                "Accept-Language": "en-IN,en;q=0.9",
                "Accept": ("text/html,application/xhtml+xml,application/xml;"
                           "q=0.9,image/webp,*/*;q=0.8"),
            },
        )
    try:
        return p.chromium.launch_persistent_context(profile_dir, **opts)
    except Exception as e:  # noqa: BLE001 - Chrome channel may be absent
        if opts.pop("channel", None):
            log.warning("Chrome channel unavailable (%s); falling back to bundled "
                        "Chromium. Install Chrome or set PROP_BROWSER_CHANNEL.", e)
            return p.chromium.launch_persistent_context(profile_dir, **opts)
        raise


# ========================================================================== Fetcher
class Fetcher:
    """Playwright + stealth fetcher for 99acres (D13). Returns raw {url, raw_html} rows.

    Defensive contract: NEVER raises. On any error (missing libs, timeout, bot wall)
    it logs and returns [] so the pipeline keeps going (SCRAPER_GUIDE). Uses a persistent
    browser profile + homepage warm-up + stealth to survive Akamai (D16) — works best on
    a residential IP, headful (set PROP_HEADLESS=0).
    """

    name = "99acres"

    def fetch(self, requirement: dict, portal_cfg: dict) -> list[dict]:
        if not _HAVE_PLAYWRIGHT:
            log.warning("playwright not installed; 99acres fetch skipped "
                        "(run `pip install -r requirements.txt && playwright install chromium`)")
            return []

        url = _build_search_url(requirement, portal_cfg)
        try:
            with pw_session() as p:  # type: ignore[misc]
                context = launch_stealth_context(p, PROFILE_DIR)
                try:
                    page = context.new_page()
                    # Warm up on the homepage so Akamai issues/matures its cookies first.
                    try:
                        page.goto(HOMEPAGE, wait_until="domcontentloaded",
                                  timeout=WAIT_TIMEOUT_MS)
                        page.wait_for_timeout(WARMUP_PAUSE_MS)
                    except Exception as e:  # noqa: BLE001
                        log.debug("99acres warmup failed (continuing): %s", e)
                    page.goto(url, wait_until="domcontentloaded",
                              timeout=WAIT_TIMEOUT_MS)
                    # Wait for result cards, NOT a fixed sleep (SCRAPER_GUIDE).
                    try:
                        page.wait_for_selector(SELECTORS["result_ready"],
                                               timeout=WAIT_TIMEOUT_MS)
                    except Exception as e:  # noqa: BLE001
                        log.warning("99acres: result selector not found at %s "
                                    "(blocked or layout changed): %s", url, e)
                    html = page.content()
                    final_url = page.url
                finally:
                    context.close()
        except Exception as e:  # noqa: BLE001 - never raise on fetch (D13/SCRAPER_GUIDE)
            log.error("99acres fetch failed for %s: %s", url, e)
            return []

        if _looks_blocked(html):
            log.warning("99acres returned a block/empty page (%d bytes) — likely Akamai "
                        "(D16). Try a residential IP and PROP_HEADLESS=0. URL: %s",
                        len(html or ""), final_url)
            return []
        # One raw row for the whole SRP page; the parser explodes it into cards (D12).
        return [{"url": final_url, "raw_html": html}]


# =========================================================================== Parser
class Parser:
    """parsel + price-parser parser for 99acres (D13). One raw SRP page -> many cards.

    Per the base.py Parser contract, parse(raw) returns a LIST of listing dicts (a raw
    row is a full SRP page containing many cards). Defensive: NEVER raises on a single
    bad card — logs and skips; returns [] if nothing parses.
    """

    name = "99acres"

    def parse(self, raw: dict) -> list[dict]:
        return self.parse_cards(raw)

    def parse_cards(self, raw: dict) -> list[dict]:
        """Extract all listing dicts from one raw SRP page. Skips bad/empty cards."""
        if not _HAVE_PARSEL:
            log.warning("parsel not installed; 99acres parse skipped")
            return []
        html = (raw or {}).get("raw_html")
        if not html:
            return []
        page_url = (raw or {}).get("url") or ""

        try:
            sel = Selector(text=html)  # type: ignore[misc]
        except Exception as e:  # noqa: BLE001
            log.error("99acres: failed to build selector: %s", e)
            return []

        listings: list[dict] = []
        cards = sel.css(SELECTORS["card"])
        for card in cards:
            try:
                listing = self._parse_one(card, page_url)
            except Exception as e:  # noqa: BLE001 - never raise on a single card
                log.warning("99acres: skipping bad card: %s", e)
                continue
            if listing is not None:
                listings.append(listing)
        if not listings:
            log.warning("99acres: 0 listings parsed from %s (selectors may be stale)",
                        page_url)
        return listings

    def _parse_one(self, card, page_url: str) -> dict | None:
        title = _first(card.css(SELECTORS["title"]).getall())
        price_text = _first(card.css(SELECTORS["price"]).getall())
        size_text = _first(card.css(SELECTORS["size"]).getall())
        location = _first(card.css(SELECTORS["location"]).getall())
        href = _first(card.css(SELECTORS["url"]).getall())
        external_id = _first(card.css(SELECTORS["external_id"]).getall())
        posted_date = _first(card.css(SELECTORS["posted_date"]).getall())

        price = normalize_price(price_text)
        size_sqm = normalize_size(size_text)
        # Skip cards missing the essentials (SCRAPER_GUIDE: missing price/size -> skip).
        if price is None or size_sqm is None:
            log.info("99acres: skipping card missing price/size "
                     "(price=%r size=%r)", price_text, size_text)
            return None

        from db import SEED_PORTALS  # base_url for resolving relative hrefs
        base_url = next((b for n, b, *_ in SEED_PORTALS if n == "99acres"),
                        "https://www.99acres.com")

        return {
            "external_id": (external_id or "").strip() or None,
            "url": _abs_url(href, base_url) or page_url,
            "title": (title or "").strip() or None,
            "price": price,
            "size_sqm": size_sqm,
            "sector": _extract_sector(location),
            "raw_location": (location or "").strip() or None,
            "posted_date": (posted_date or "").strip() or None,
        }


def _first(values: list[str] | None) -> str | None:
    if not values:
        return None
    for v in values:
        if v and v.strip():
            return v.strip()
    return None


# Self-register with the loader (D13). base.py imports this module to trigger this.
try:
    from scrapers.base import register
    register("99acres", Fetcher, Parser)
except Exception:  # noqa: BLE001 - registration is best-effort (e.g. odd import paths)
    pass


# =================================================================== offline self-test
if __name__ == "__main__":
    # Pure-offline tests of the normalization helpers — no network, no scraping libs.
    print("normalize_price:")
    cases_price = [
        ("Rs 4.25 Cr", 42_500_000),
        ("₹4.25 Cr", 42_500_000),
        ("4.5 Crore", 45_000_000),
        ("4,25,00,000", 42_500_000),
        ("85 Lakh", 8_500_000),
        ("85 Lac", 8_500_000),
        ("", None),
        ("Price on request", None),
    ]
    for text, expected in cases_price:
        got = normalize_price(text)
        print(f"  {text!r:24} -> {got!r:>12}  (expected {expected!r})")
        assert got == expected, f"normalize_price({text!r}) = {got!r}, want {expected!r}"

    print("normalize_size:")
    cases_size = [
        ("250 sq.yd", 209.03),     # 250 * 0.836127
        ("250 sqyd", 209.03),
        ("1200 sq.ft", 111.48),    # 1200 * 0.092903
        ("1200 sqft", 111.48),
        ("1,200 sq.ft.", 111.48),
        ("112 sq.m", 112.0),
        ("162 sqm", 162.0),
        ("1500", 139.35),          # bare number -> assume sqft
        ("", None),
        ("N/A", None),
    ]
    for text, expected in cases_size:
        got = normalize_size(text)
        print(f"  {text!r:24} -> {got!r:>10}  (expected {expected!r})")
        assert got == expected, f"normalize_size({text!r}) = {got!r}, want {expected!r}"

    print("_extract_sector:")
    for text, expected in [
        ("Sector 50, Noida", "Sector 50"),
        ("sector-104 noida", "Sector 104"),
        ("Greater Noida West", None),
    ]:
        got = _extract_sector(text)
        print(f"  {text!r:24} -> {got!r}  (expected {expected!r})")
        assert got == expected

    print("\nAll normalization assertions passed.")
