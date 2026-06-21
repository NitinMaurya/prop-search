"""Shared scraper infrastructure (D14/D26): optional-library guards, Indian-number
normalization, and the Patchright/Playwright browser-launch helpers.

Extracted verbatim from the v1 99acres plugin — every portal fetcher drives the browser
identically, so the stealth rules live in one place. MagicBricks imports from here.
"""

import logging
import os
import re

log = logging.getLogger(__name__)

# --------------------------------------------------------------- optional library guards
# Prefer Patchright (D26): a drop-in Playwright replacement that patches the automation
# fingerprints Akamai/Cloudflare detect. Fall back to vanilla Playwright if absent.
try:
    from patchright.sync_api import sync_playwright  # type: ignore
    _HAVE_PLAYWRIGHT = True
    _USING_PATCHRIGHT = True
except ImportError:  # pragma: no cover
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
        _HAVE_PLAYWRIGHT = True
    except ImportError:
        sync_playwright = None  # type: ignore
        _HAVE_PLAYWRIGHT = False
    _USING_PATCHRIGHT = False

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

# ============================================================== constants
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
VIEWPORT = {"width": 1366, "height": 900}
WAIT_TIMEOUT_MS = 25000
WARMUP_PAUSE_MS = 2500

SQFT_TO_SQM = 0.092903
SQYD_TO_SQM = 0.836127
CRORE = 10_000_000   # 1e7
LAKH = 100_000       # 1e5

# Persistent profile dir so Akamai cookies (_abck / bm_sz) mature across runs. Override the
# parent via PROP_DATA_DIR (e.g. on the India box); defaults to ./data next to the cwd.
_DATA_DIR = os.environ.get("PROP_DATA_DIR", os.path.join(os.getcwd(), "data"))
PROFILE_DIR = os.path.join(_DATA_DIR, ".pw-99acres-profile")  # MagicBricks .replace()s this

# Default HEADFUL (D26): a visible real browser on a residential IP is what beats Akamai.
HEADLESS = os.environ.get("PROP_HEADLESS", "0") == "1"
# Patchright drives real Chrome best. Override via PROP_BROWSER_CHANNEL; empty = bundled.
BROWSER_CHANNEL = os.environ.get("PROP_BROWSER_CHANNEL", "chrome")

BLOCK_MARKERS = ("Access Denied", "You don't have permission", "Request unsuccessful",
                 "captcha", "Pardon Our Interruption", "Request Blocked", "Security Alert",
                 "suspicious activity")


# ===================================================================== normalization
def normalize_price(text: str | None) -> int | None:
    """Parse an Indian price string to integer rupees, or None if unparseable.
    Handles 'Rs 4.25 Cr', '4.5 Crore', '85 Lakh', plain '4,25,00,000'."""
    if not text:
        return None
    t = str(text).strip()
    if not t:
        return None
    low = t.lower()
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
        m = re.search(r"[\d][\d,]*\.?\d*", t)
        if not m:
            return None
        try:
            amount = float(m.group(0).replace(",", ""))
        except ValueError:
            return None
    rupees = int(round(amount * multiplier))
    return rupees if rupees > 0 else None


def normalize_size(text: str | None) -> float | None:
    """Parse an area string to square metres (float), or None. Bare number -> sqft."""
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
    if re.search(r"sq\.?\s*y(?:d|rd|ard|ds|rds)?\b|sqyrd|\bgaj\b|\byards?\b", t):
        return round(value * SQYD_TO_SQM, 2)
    if re.search(r"sq\.?\s*m(?:t|tr|eter|etre)?\b|sqm|\bsq\.?\s*metre", t):
        return round(value, 2)
    return round(value * SQFT_TO_SQM, 2)


def _extract_sector(location: str | None) -> str | None:
    """Pull a normalized 'Sector N' out of a raw location string, if present."""
    if not location:
        return None
    m = re.search(r"sector[\s-]*([0-9]+[a-z]?)", location, re.IGNORECASE)
    if m:
        return f"Sector {m.group(1).upper()}"
    return None


def _looks_blocked(html: str) -> bool:
    """Detect an Akamai/anti-bot block page vs. a real SRP (D16)."""
    if not html or len(html) < 1500:
        return True
    return any(marker.lower() in html.lower() for marker in BLOCK_MARKERS)


# ------------------------------------------------- shared browser launch helpers (D26)
def pw_session():
    """Playwright/Patchright context manager for `with ... as p`. With vanilla Playwright
    we wrap in playwright-stealth; with Patchright we don't (it IS the stealth layer)."""
    if not _USING_PATCHRIGHT:
        try:
            from playwright_stealth import Stealth  # type: ignore
            return Stealth().use_sync(sync_playwright())
        except Exception:  # noqa: BLE001
            pass
    return sync_playwright()  # type: ignore[misc]


def launch_stealth_context(p, profile_dir: str):
    """Launch a persistent browser context tuned for anti-bot evasion (D26)."""
    os.makedirs(profile_dir, exist_ok=True)
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
