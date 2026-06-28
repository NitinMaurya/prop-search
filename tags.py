"""Derived listing labels parsed from free text (title + description).

Pure, read-layer feature: no DB columns, no re-scrape. The app calls `extract(listing)`
on already-stored listings to surface two facts buyers care about but portals bury in the
blurb:

  • facing direction  — "north facing", "facing north-east", "east-facing" -> "North-East"
  • park-facing       — "overlooking the park", "facing a park", "park facing" -> True

Kept deliberately small (regex over text); see CLAUDE.md — do not over-engineer. The 8
compass labels in DIRECTIONS double as the UI filter options.
"""

import re

# Canonical labels, in compass order. Used as the facing-filter options in the UI.
DIRECTIONS = ["North", "South", "East", "West",
              "North-East", "North-West", "South-East", "South-West"]

# Short forms for compact chips/labels (N, NE, ...).
ABBR = {"North": "N", "South": "S", "East": "E", "West": "W",
        "North-East": "NE", "North-West": "NW",
        "South-East": "SE", "South-West": "SW"}

# Compound directions are listed first so the regex alternation prefers them over the
# bare "north"/"east" that they contain.
_DIR = (r"north[\s\-/]?east|north[\s\-/]?west|south[\s\-/]?east|south[\s\-/]?west"
        r"|north|south|east|west")

# A direction sitting next to a "facing" word, in either order:
#   "<dir> facing"  ("north-east facing", "east facing", "west faced")
#   "facing <dir>"  ("facing north east", "facing: south")
_FACING_RE = re.compile(
    rf"(?:({_DIR})[\s\-]*(?:facing|faced|face))|(?:facing[\s:\-]*({_DIR}))", re.I)

# "park facing", or a proximity word ("overlooking / facing / in front of / opposite /
# adjacent to ...") followed within a few words by "park".
_PARK_RE = re.compile(
    r"park[\s\-]?facing"
    r"|(?:overlook(?:s|ing)?|facing|in\s+front\s+of|front\s+of|opposite"
    r"|adjoining|adjacent\s+to|abut(?:s|ting)?|next\s+to|besides?)"
    r"\s+(?:the\s+|a\s+)?(?:[a-z0-9]+\s+){0,3}park",
    re.I)

_COMPOUND = {"northeast": "North-East", "northwest": "North-West",
             "southeast": "South-East", "southwest": "South-West"}
_SIMPLE = {"north": "North", "south": "South", "east": "East", "west": "West"}


def _canon(token: str) -> str | None:
    t = re.sub(r"[\s\-/]", "", token.lower())
    return _COMPOUND.get(t) or _SIMPLE.get(t)


def facing(text: str | None) -> str | None:
    """First compass direction described as the property's facing, or None.
    Returns one of DIRECTIONS, e.g. "North-East"."""
    if not text:
        return None
    m = _FACING_RE.search(text)
    if not m:
        return None
    return _canon(m.group(1) or m.group(2))


def park_facing(text: str | None) -> bool:
    """True if the text says the property faces / overlooks / fronts a park."""
    return bool(text and _PARK_RE.search(text))


def extract(listing: dict) -> dict:
    """Derived labels for one listing dict. Reads title + description.
    Returns {"facing": <label|None>, "park": <bool>}."""
    text = " ".join(str(listing.get(k) or "") for k in ("title", "description"))
    return {"facing": facing(text), "park": park_facing(text)}
