"""Plugin interfaces + registry (D13). Fetcher produces raw pages; Parser turns one raw
page into clean listing dicts. Both keyed by portal name. v2 ships MagicBricks only;
99acres / Housing.com are re-added here once verified from the India residential IP.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Fetcher(Protocol):
    name: str

    def fetch(self, requirement: dict, portal_cfg: dict) -> list[dict]:
        """Fetch search results for one requirement. Returns raw rows {url, raw_html}.
        Must not raise on a single bad page — skip and continue."""
        ...


@runtime_checkable
class Parser(Protocol):
    name: str

    def parse(self, raw: dict) -> list[dict]:
        """Turn ONE raw page into 0..N clean listing dicts. Must not raise on a bad card."""
        ...


# --------------------------------------------------------------------- plugin registry
_REGISTRY: dict[str, dict[str, type]] = {}
_PLUGIN_MODULES = ["prop_search_core.scrapers.magicbricks"]
_loaded = False


def register(name: str, fetcher_cls: type, parser_cls: type) -> None:
    _REGISTRY[name] = {"fetcher": fetcher_cls, "parser": parser_cls}


def _ensure_loaded() -> None:
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
    _ensure_loaded()
    entry = _REGISTRY.get(name)
    return entry["fetcher"]() if entry else None


def get_parser(name: str) -> Parser | None:
    _ensure_loaded()
    entry = _REGISTRY.get(name)
    return entry["parser"]() if entry else None


def registered_portals() -> list[str]:
    _ensure_loaded()
    return sorted(_REGISTRY)
