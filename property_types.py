"""Property-type taxonomy (D19).

A requirement picks ONE high-level category (house / plot / apartment). Each category
expands two ways:
  - SEARCH:   the portal SRP URL with the right proptype tokens, so we fetch the right
              KIND of property at the source (server-side filter) — not scrape-then-drop.
  - MATCHING: a synonym list so a listing titled "Kothi", "Villa" or "Independent House"
              all read as the same category, and a "Plot" is recognised as a different
              one (matcher.property_type_fit).

Kept in code, not the DB, per the repo convention: portal config/parsing lives in code;
the user's *choice* lives in requirements.property_type (it stores a key from CATEGORIES).
One category per requirement keeps it simple (D1) — for two kinds, make two requirements.

The MagicBricks URLs use the proptype tokens confirmed from the live filter API
(fetch-filter-data otherDataMap): House/Villa, Residential-Plot, and the four flat types.
"""

CATEGORIES = {
    "house": {
        "label": "Independent House / Kothi / Villa",
        # Substrings matched (lowercased) against a listing title.
        "synonyms": ["kothi", "independent house", "independent home", "villa",
                     "bungalow", "duplex", "house"],
        "magicbricks": ("https://www.magicbricks.com/property-for-sale/"
                        "residential-real-estate?proptype=Residential-House,Villa"
                        "&cityName=Noida"),
    },
    "plot": {
        "label": "Plot / Land",
        "synonyms": ["plot", "residential plot", "land", "gaj"],
        "magicbricks": ("https://www.magicbricks.com/property-for-sale/"
                        "residential-real-estate?proptype=Residential-Plot"
                        "&cityName=Noida"),
    },
    "apartment": {
        "label": "Apartment / Flat",
        "synonyms": ["apartment", "flat", "builder floor", "penthouse", "studio",
                     "multistorey", "multistorey apartment"],
        "magicbricks": ("https://www.magicbricks.com/property-for-sale/"
                        "residential-real-estate?proptype=Multistorey-Apartment,"
                        "Builder-Floor-Apartment,Penthouse,Studio-Apartment"
                        "&cityName=Noida"),
    },
}

DEFAULT_CATEGORY = "house"

# Legacy / free-text values (older requirements stored "kothi") -> a canonical key.
_ALIASES = {
    "kothi": "house", "independent house": "house", "villa": "house",
    "bungalow": "house", "house": "house", "duplex": "house",
    "plot": "plot", "land": "plot",
    "apartment": "apartment", "flat": "apartment",
}


def category_of(property_type) -> str:
    """Canonical category key for a stored property_type (handles legacy 'kothi')."""
    if not property_type:
        return DEFAULT_CATEGORY
    key = str(property_type).strip().lower()
    if key in CATEGORIES:
        return key
    return _ALIASES.get(key, DEFAULT_CATEGORY)


def label_of(property_type) -> str:
    """Human label for a stored property_type, e.g. 'Independent House / Kothi / Villa'."""
    return CATEGORIES[category_of(property_type)]["label"]


def synonyms_for(property_type) -> list[str]:
    """Synonym substrings for a category (used by the matcher to recognise the type)."""
    return CATEGORIES[category_of(property_type)]["synonyms"]


def search_url(portal_key: str, property_type) -> str | None:
    """Portal SRP URL for a category, or None if that portal isn't mapped.
    portal_key is the lowercased portal key, e.g. 'magicbricks'."""
    return CATEGORIES[category_of(property_type)].get(portal_key)


# Choices for the Streamlit form: [(key, label), ...] in display order.
def choices() -> list[tuple[str, str]]:
    return [(k, v["label"]) for k, v in CATEGORIES.items()]
