"""Plugin interfaces (D13). See docs/SCRAPER_GUIDE.md for the full contract.

Fetch and parse are decoupled by the `raw_listings` staging table (D12). A portal has
a Fetcher (produces raw rows) and a Parser (raw -> clean listing). Both keyed by
portals.name. Either can be swapped without touching the other or the pipeline.

Stage 1 — Fetcher: fetch + store raw. Default impl uses Playwright + playwright-stealth.
Stage 2 — Parser: raw HTML -> fields, using parsel/bs4 + price-parser (D14).

This module also exposes a tiny module-level plugin registry. Plugin modules (e.g.
scrapers/nineacres.py) call `register(name, FetcherCls, ParserCls)` at import time;
the pipeline resolves a portals.name string to instances via `get_fetcher(name)` /
`get_parser(name)`.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Fetcher(Protocol):
    name: str  # must equal portals.name, e.g. "99acres"

    def fetch(self, requirement: dict, portal_cfg: dict) -> list[dict]:
        """Fetch search results for one requirement on this portal.
        Returns raw rows: {url, raw_html} (the pipeline stamps fetched_at/status).
        Must not raise on a single bad page — skip and continue. No parsing here.
        """
        ...


@runtime_checkable
class Parser(Protocol):
    name: str  # must equal portals.name

    def parse(self, raw: dict) -> list[dict]:
        """Turn ONE raw_listings row into a list of clean listing dicts.
        A raw row is typically a whole search-results page containing many cards, so
        parse() returns 0..N listings (empty list if none/unparseable — never None).
        Required keys per listing: external_id, url, title, price (int rupees),
        size_sqm (float), sector, raw_location, posted_date (or None).
        Use parsel/bs4 for selection and price-parser for money. Skip bad/missing
        price/size cards; the pipeline computes fingerprint/timestamps and upserts.
        Must not raise on a single bad card — skip and continue.
        """
        ...


# --------------------------------------------------------------------- plugin registry
# Keyed by portals.name. A simple module-level dict is enough for an MVP (D1) — there
# are a handful of portals and one process. Plugin modules self-register at import time.
_REGISTRY: dict[str, dict[str, type]] = {}

# Known plugin modules to import so they self-register on first registry access. Keep
# this list in sync when adding a portal plugin (D3/D13). Import is lazy + best-effort:
# a plugin that fails to import (e.g. a syntax error) must not break other portals.
_PLUGIN_MODULES = ["scrapers.nineacres", "scrapers.magicbricks", "scrapers.housing"]
_loaded = False


def register(name: str, fetcher_cls: type, parser_cls: type) -> None:
    """Register a portal's Fetcher + Parser classes under portals.name."""
    _REGISTRY[name] = {"fetcher": fetcher_cls, "parser": parser_cls}


def _ensure_loaded() -> None:
    """Import known plugin modules once so they self-register (best-effort)."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    import importlib
    for mod in _PLUGIN_MODULES:
        try:
            importlib.import_module(mod)
        except Exception as e:  # noqa: BLE001 - a bad plugin must not kill the registry
            import logging
            logging.getLogger(__name__).warning(
                "scraper plugin %s failed to import: %s", mod, e)


def get_fetcher(name: str) -> Fetcher | None:
    """Return a fresh Fetcher instance for a portal name, or None if unregistered."""
    _ensure_loaded()
    entry = _REGISTRY.get(name)
    return entry["fetcher"]() if entry else None


def get_parser(name: str) -> Parser | None:
    """Return a fresh Parser instance for a portal name, or None if unregistered."""
    _ensure_loaded()
    entry = _REGISTRY.get(name)
    return entry["parser"]() if entry else None


def registered_portals() -> list[str]:
    """Names of portals that have a registered plugin (loads plugins first)."""
    _ensure_loaded()
    return sorted(_REGISTRY)
