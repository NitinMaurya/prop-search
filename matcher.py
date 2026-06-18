"""Matching — score listings against requirements (D5: tolerance band + score).

score = W_SIZE*size_closeness + W_PRICE*price_fit + W_SECTOR*sector_fit   (0..1)
  size_closeness: 1.0 at a target size in requirement.sizes_sqm, decays past tolerance.
  price_fit:      1.0 within [budget_min, budget_max], decays above the soft cap.
  sector_fit:     1.0 if listing.sector in requirement.sectors (empty sectors = all).

Public surface (build step 4):
  score(listing: dict, requirement: dict) -> float
  matches_for(requirement, listings) -> list[(listing, score)] above THRESHOLD

PURE module: no DB, no I/O, no network. Inputs are the plain dicts that
db.list_requirements() and db.list_active_listings() return.
"""

# --- tunable knobs -----------------------------------------------------------
# DEFAULTS are the fallback when no cfg is passed. At runtime these are overridden
# live from the DB (db.matcher_config(), D17) — this module stays PURE (no DB import);
# the caller passes cfg into score()/matches_for(). Weights sum to 1.0 so score is 0..1.
DEFAULTS = {
    "threshold": 0.6,           # match cutoff (D5)
    "w_size": 0.4,              # weight: size closeness
    "w_price": 0.4,             # weight: price fit
    "w_sector": 0.2,            # weight: sector fit
    "budget_softcap_pct": 0.05,  # allow ~5% over budget_max as a decaying near-match
    "sector_miss_fit": 0.3,      # a wrong sector still scores a little (ranked near-miss)
}
# Back-compat module constants (used by the self-test and any direct importer).
W_SIZE = DEFAULTS["w_size"]
W_PRICE = DEFAULTS["w_price"]
W_SECTOR = DEFAULTS["w_sector"]
THRESHOLD = DEFAULTS["threshold"]
BUDGET_SOFTCAP_PCT = DEFAULTS["budget_softcap_pct"]
SECTOR_MISS_FIT = DEFAULTS["sector_miss_fit"]


def _cfg(cfg) -> dict:
    """Merge a partial cfg over DEFAULTS so any missing key falls back safely."""
    return {**DEFAULTS, **(cfg or {})}


# --- helpers -----------------------------------------------------------------
def _norm_sector(s) -> str:
    """Normalize a sector string for case/whitespace-insensitive comparison.

    "Sector 50", "sector 50", " SECTOR  50 " all collapse to "sector 50".
    """
    return " ".join(str(s).strip().lower().split())


def size_closeness(size_sqm, sizes_sqm, tolerance_pct) -> float:
    """1.0 if size_sqm is within tolerance of ANY target size; decays to 0 beyond.

    Empty target list -> neutral 1.0 (no size constraint). Missing/None size ->
    0.0 (a listing with no size is a weak size match, but never raises).
    The decay band past tolerance is the same width as the tolerance band itself,
    so closeness reaches 0 at ~2x the tolerance distance from a target.
    """
    if not sizes_sqm:
        return 1.0
    if size_sqm is None:
        return 0.0

    tol = (tolerance_pct or 0) / 100.0
    best = 0.0
    for target in sizes_sqm:
        if not target:
            continue
        band = target * tol            # absolute tolerance width in sqm
        dist = abs(size_sqm - target)
        if dist <= band:
            closeness = 1.0
        elif band <= 0:
            # zero tolerance: only an exact hit counts; anything else is a miss.
            closeness = 0.0
        else:
            # linear decay across one extra band width past tolerance, then 0.
            over = dist - band
            closeness = max(0.0, 1.0 - over / band)
        best = max(best, closeness)
    return best


def price_fit(price, budget_min, budget_max, softcap_pct=BUDGET_SOFTCAP_PCT) -> float:
    """1.0 inside [budget_min, budget_max]; below min is also fine (cheaper is good);
    above max decays linearly to 0 across the soft cap (budget_max*(1+softcap)).

    Missing/None price -> 0.5 (neutral-ish: don't reward, don't fully punish; never raise).
    Below-budget is treated as a full match (1.0): a cheaper kothi meeting size/sector
    is still a great find in a thin resale market (D5).
    """
    if price is None:
        return 0.5
    if budget_max is None:
        return 1.0
    if price <= budget_max:
        # at or under the cap (incl. below budget_min) -> full price fit.
        return 1.0
    softcap = budget_max * (1.0 + softcap_pct)
    if price >= softcap or softcap <= budget_max:
        return 0.0
    return max(0.0, 1.0 - (price - budget_max) / (softcap - budget_max))


def sector_fit(sector, sectors, miss_fit=SECTOR_MISS_FIT) -> float:
    """1.0 if listing sector matches any required sector (case/space-insensitive);
    empty requirement sectors -> 1.0 (all of Noida). Non-match -> miss_fit.
    Missing/None listing sector with a constrained requirement -> miss_fit.
    """
    if not sectors:
        return 1.0
    if not sector:
        return miss_fit
    wanted = {_norm_sector(s) for s in sectors}
    return 1.0 if _norm_sector(sector) in wanted else miss_fit


# --- public surface ----------------------------------------------------------
def score(listing: dict, requirement: dict, cfg: dict | None = None) -> float:
    """Weighted 0..1 score of how well a listing fits a requirement (D5).
    cfg (from db.matcher_config(), D17) overrides weights/softcap/sector_miss_fit;
    omit it to use DEFAULTS. Size tolerance is per-requirement, not in cfg."""
    c = _cfg(cfg)
    s = size_closeness(
        listing.get("size_sqm"),
        requirement.get("sizes_sqm") or [],
        requirement.get("size_tolerance_pct"),
    )
    p = price_fit(
        listing.get("price"),
        requirement.get("budget_min"),
        requirement.get("budget_max"),
        c["budget_softcap_pct"],
    )
    sec = sector_fit(listing.get("sector"), requirement.get("sectors") or [],
                     c["sector_miss_fit"])
    return c["w_size"] * s + c["w_price"] * p + c["w_sector"] * sec


def matches_for(requirement: dict, listings: list[dict],
                cfg: dict | None = None) -> list[tuple[dict, float]]:
    """(listing, score) pairs scoring >= threshold, sorted by score descending.
    cfg overrides the knobs incl. the threshold (D17); omit for DEFAULTS."""
    c = _cfg(cfg)
    scored = [(l, score(l, requirement, c)) for l in listings]
    scored = [pair for pair in scored if pair[1] >= c["threshold"]]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


if __name__ == "__main__":
    assert abs(W_SIZE + W_PRICE + W_SECTOR - 1.0) < 1e-9, "weights must sum to 1.0"

    # The first real requirement (D9/Q2): a kothi, 112/162 sqm ±10%, 4-4.5cr, Sector 50.
    req = {
        "sizes_sqm": [112, 162],
        "size_tolerance_pct": 10,
        "budget_min": 40000000,
        "budget_max": 45000000,
        "sectors": ["Sector 50"],
    }

    # 1) Exact match: right size, in budget, right sector -> high score.
    exact = {"size_sqm": 112, "price": 43000000, "sector": "Sector 50"}
    exact_score = score(exact, req)
    assert exact_score == 1.0, exact_score

    # 2) Over-budget decays: ~3% over max is within the 5% soft cap -> partial price_fit,
    #    so total drops below the exact match but stays above 0.
    over = {"size_sqm": 112, "price": 46350000, "sector": "Sector 50"}  # +3% over max
    over_score = score(over, req)
    assert exact_score > over_score > THRESHOLD, (exact_score, over_score)

    # 3) Wrong sector scores lower than a matching sector (otherwise identical).
    wrong_sector = {"size_sqm": 112, "price": 43000000, "sector": "Sector 99"}
    wrong_score = score(wrong_sector, req)
    assert wrong_score < exact_score, (wrong_score, exact_score)
    # case-insensitive sector match: "sector 50" must equal "Sector 50".
    assert score({"size_sqm": 112, "price": 43000000, "sector": "sector 50"}, req) == 1.0

    # matches_for ranks descending and drops sub-threshold listings.
    ranked = matches_for(req, [over, wrong_sector, exact])
    assert ranked[0][0] is exact, ranked
    assert all(s >= THRESHOLD for _, s in ranked)

    # Missing fields never raise.
    assert 0.0 <= score({"price": None, "size_sqm": None, "sector": None}, req) <= 1.0

    print("matcher self-tests passed:")
    print(f"  exact={exact_score:.3f}  over_budget={over_score:.3f}  "
          f"wrong_sector={wrong_score:.3f}  threshold={THRESHOLD}")
    print(f"  ranked matches: {[round(s, 3) for _, s in ranked]}")
