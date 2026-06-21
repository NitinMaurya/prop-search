"""Tiny in-process TTL cache. The data is read-heavy and changes infrequently (listings
update ~every 6h; a user's own feedback/tracking changes are invalidated explicitly), so
caching avoids the ~hundreds-of-ms DB round-trip on repeat reads.

Per-process (each API instance has its own); fine at this scale. Cross-process freshness
is bounded by the TTL (e.g. a scrape's new matches appear within MATCHES_TTL seconds).
"""

import time

_store: dict[str, tuple[float, object]] = {}


def get(key: str):
    entry = _store.get(key)
    if entry and entry[0] > time.monotonic():
        return entry[1]
    _store.pop(key, None)
    return None


def put(key: str, value, ttl: float) -> None:
    _store[key] = (time.monotonic() + ttl, value)


def invalidate(key: str) -> None:
    _store.pop(key, None)


def clear() -> None:
    _store.clear()
