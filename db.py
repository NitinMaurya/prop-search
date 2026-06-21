"""Data layer — owns the SQLite schema and all queries.

Single source of truth for the data model. See docs/ARCHITECTURE.md for table specs and
docs/DECISIONS.md (D1 simple, D7 fingerprint dedup, D9 requirements CRUD, D12 raw
staging, D15 runs/observability).

This module's PUBLIC FUNCTIONS are the frozen contract other modules code against:
  init()
  # requirements — full CRUD, user data, never hardcoded (D9)
  add_requirement(...) / list_requirements(active_only=False) /
    update_requirement(req_id, **fields) / deactivate_requirement(req_id)
  # portals
  list_enabled_portals() / update_portal_last_run(portal_id)
  # raw staging boundary (D12): fetch writes raw; parse reads pending -> listings
  add_raw(portal_id, url, raw_html) / pending_raw() /
    mark_raw_parsed(raw_id) / mark_raw_error(raw_id, msg) / reset_raw_pending(portal_id)
  # listings — dedup by fingerprint (D7)
  upsert_listing(listing: dict) -> listing_id
  list_active_listings()
  mark_stale(threshold_runs=3)
  # matches
  record_match(req_id, listing_id, score) / unnotified_matches() / mark_notified(match_id)
  # observability (D15)
  start_run() -> run_id / finish_run(run_id, **counts) /
    recent_runs(limit=20) / status_summary()

DB file: data/prop_search.db
"""

import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "prop_search.db")

# Seeded portals (D4). search_url_template placeholders: {sector} {price_min}
# {price_max} {size}. Templates are starting points — refine per scraper in step 3/6.
SEED_PORTALS = [
    ("99acres", "https://www.99acres.com",
     "https://www.99acres.com/independent-house-villas-for-sale-in-noida-ffid", 1),
    ("MagicBricks", "https://www.magicbricks.com",
     "https://www.magicbricks.com/independent-house-for-sale-in-noida-pppfs", 1),
    ("Housing.com", "https://housing.com",
     "https://housing.com/in/buy/noida/noida?property_type=independent_house", 1),
    ("NoBroker", "https://www.nobroker.in",
     "https://www.nobroker.in/property/sale/noida/multiple", 0),  # disabled: bot walls
]

HOURS_PER_RUN = 6  # cadence; used by mark_stale to translate "missed runs" -> time

# Global tuning knobs, editable live from the DB (D17). matcher.py stays pure: the
# scheduler/app read these and pass them in. Keys mirror matcher.DEFAULTS.
SEED_SETTINGS = {
    "threshold": 0.6,            # min score to count as a match
    "w_size": 0.4,               # weight: size closeness
    "w_price": 0.4,              # weight: price fit
    "w_sector": 0.2,             # weight: sector fit
    "budget_softcap_pct": 0.05,  # allowed % over budget_max before price_fit hits 0
    "sector_miss_fit": 0.3,      # score for a non-matching sector
    "type_miss_fit": 0.0,        # D19: multiplier for a wrong-category listing (0 = drop)
    "noida_authority_only": 1,   # D21: keep only NOIDA-authority, non-freehold listings
    "stale_threshold_runs": 3,   # Q3: missed runs before a listing is marked stale
}


# ----------------------------------------------------------------------------- helpers
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def fingerprint(price, size_sqm, sector, title) -> str:
    """Dedup key (D7): normalized price + size + sector + fuzzy title."""
    price_bucket = round((price or 0) / 100000)          # nearest lakh
    size_bucket = round((size_sqm or 0))                 # nearest sqm
    sector_norm = re.sub(r"\s+", " ", (sector or "").strip().lower())
    title_tokens = sorted(re.findall(r"[a-z0-9]+", (title or "").lower()))
    basis = f"{price_bucket}|{size_bucket}|{sector_norm}|{' '.join(title_tokens)}"
    return hashlib.sha1(basis.encode()).hexdigest()


# -------------------------------------------------------------------------------- init
def init() -> None:
    """Create tables if absent and seed portals (idempotent)."""
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS requirements (
                id                 INTEGER PRIMARY KEY,
                owner              TEXT NOT NULL,
                property_type      TEXT NOT NULL DEFAULT 'house',  -- key from property_types.CATEGORIES (D19)
                sizes_sqm          TEXT NOT NULL DEFAULT '[]',   -- JSON list
                size_tolerance_pct REAL NOT NULL DEFAULT 30,
                budget_min         INTEGER NOT NULL,
                budget_max         INTEGER NOT NULL,
                sectors            TEXT NOT NULL DEFAULT '[]',    -- JSON list, [] = all
                active             INTEGER NOT NULL DEFAULT 1,
                created_at         TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS portals (
                id                  INTEGER PRIMARY KEY,
                name                TEXT UNIQUE NOT NULL,
                base_url            TEXT NOT NULL,
                search_url_template TEXT NOT NULL,
                enabled             INTEGER NOT NULL DEFAULT 1,
                last_run_at         TEXT
            );

            CREATE TABLE IF NOT EXISTS raw_listings (
                id           INTEGER PRIMARY KEY,
                portal_id    INTEGER NOT NULL REFERENCES portals(id),
                url          TEXT,
                raw_html     TEXT,
                fetched_at   TEXT NOT NULL,
                parse_status TEXT NOT NULL DEFAULT 'pending',  -- pending|parsed|error
                parse_error  TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_raw_status ON raw_listings(parse_status);

            CREATE TABLE IF NOT EXISTS listings (
                id            INTEGER PRIMARY KEY,
                portal_id     INTEGER NOT NULL REFERENCES portals(id),
                external_id   TEXT,
                url           TEXT,
                title         TEXT,
                price         INTEGER,
                size_sqm      REAL,
                sector        TEXT,
                raw_location  TEXT,
                posted_date   TEXT,
                image_url     TEXT,
                advertiser    TEXT,
                ownership     TEXT,
                approving_authority TEXT,
                description   TEXT,
                fingerprint   TEXT UNIQUE NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at  TEXT NOT NULL,
                is_stale      INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS matches (
                id             INTEGER PRIMARY KEY,
                requirement_id INTEGER NOT NULL REFERENCES requirements(id),
                listing_id     INTEGER NOT NULL REFERENCES listings(id),
                score          REAL NOT NULL,
                notified       INTEGER NOT NULL DEFAULT 0,
                created_at     TEXT NOT NULL,
                UNIQUE(requirement_id, listing_id)
            );

            CREATE TABLE IF NOT EXISTS runs (
                id           INTEGER PRIMARY KEY,
                started_at   TEXT NOT NULL,
                finished_at  TEXT,
                portals_run  INTEGER DEFAULT 0,
                raw_fetched  INTEGER DEFAULT 0,
                parsed_ok    INTEGER DEFAULT 0,
                parse_errors INTEGER DEFAULT 0,
                new_matches  INTEGER DEFAULT 0,
                notified     INTEGER DEFAULT 0,
                error        TEXT
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value REAL NOT NULL
            );

            -- Shortlist: user's like/dislike per listing (UI feature). One verdict per
            -- listing; persists independently of matches so liked homes can be followed
            -- up later even after they leave the matches view.
            CREATE TABLE IF NOT EXISTS feedback (
                listing_id INTEGER PRIMARY KEY REFERENCES listings(id) ON DELETE CASCADE,
                verdict    TEXT NOT NULL,            -- 'like' | 'nope'
                reason     TEXT,                     -- why passed: over_budget|fake|... (NULL otherwise)
                updated_at TEXT NOT NULL
            );

            -- Follow-up tracking (D29): which listings you've contacted + free-text notes.
            -- Independent of like/pass so you can track a listing without rating it.
            CREATE TABLE IF NOT EXISTS tracking (
                listing_id   INTEGER PRIMARY KEY REFERENCES listings(id) ON DELETE CASCADE,
                contacted_at TEXT,                   -- ISO ts when marked contacted, NULL = not
                notes        TEXT,                    -- free-text follow-up notes
                updated_at   TEXT NOT NULL
            );
            """
        )
        # Migrate older DBs that predate the image_url/advertiser columns (D20).
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(listings)")}
        for col in ("image_url", "advertiser", "ownership", "approving_authority",
                    "description"):
            if col not in cols:
                conn.execute(f"ALTER TABLE listings ADD COLUMN {col} TEXT")
        # Migrate older DBs that predate the feedback.reason column (D29).
        fb_cols = {r["name"] for r in conn.execute("PRAGMA table_info(feedback)")}
        if "reason" not in fb_cols:
            conn.execute("ALTER TABLE feedback ADD COLUMN reason TEXT")
        for key, value in SEED_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                         (key, value))
        for name, base_url, tmpl, enabled in SEED_PORTALS:
            conn.execute(
                "INSERT OR IGNORE INTO portals (name, base_url, search_url_template, "
                "enabled) VALUES (?, ?, ?, ?)",
                (name, base_url, tmpl, enabled),
            )


# ------------------------------------------------------------------------ requirements
def add_requirement(owner, budget_min, budget_max, sizes_sqm=None, sectors=None,
                    property_type="house", size_tolerance_pct=30) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO requirements (owner, property_type, sizes_sqm, "
            "size_tolerance_pct, budget_min, budget_max, sectors, active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (owner, property_type, json.dumps(sizes_sqm or []), size_tolerance_pct,
             budget_min, budget_max, json.dumps(sectors or []), _now()),
        )
        return cur.lastrowid


def _row_to_requirement(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["sizes_sqm"] = json.loads(d["sizes_sqm"])
    d["sectors"] = json.loads(d["sectors"])
    return d


def list_requirements(active_only=False) -> list[dict]:
    q = "SELECT * FROM requirements"
    if active_only:
        q += " WHERE active = 1"
    q += " ORDER BY created_at DESC"
    with connect() as conn:
        return [_row_to_requirement(r) for r in conn.execute(q)]


def update_requirement(req_id, **fields) -> None:
    """Update any of: owner, property_type, sizes_sqm, size_tolerance_pct, budget_min,
    budget_max, sectors, active. List fields are JSON-encoded automatically."""
    if not fields:
        return
    for k in ("sizes_sqm", "sectors"):
        if k in fields:
            fields[k] = json.dumps(fields[k])
    cols = ", ".join(f"{k} = ?" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE requirements SET {cols} WHERE id = ?",
                     (*fields.values(), req_id))


def deactivate_requirement(req_id) -> None:
    with connect() as conn:
        conn.execute("UPDATE requirements SET active = 0 WHERE id = ?", (req_id,))


def delete_requirement(req_id) -> None:
    """Permanently remove a requirement (CRUD delete). Matches reference requirement_id
    but have no FK cascade here, so they simply stop being tied to a live requirement."""
    with connect() as conn:
        conn.execute("DELETE FROM requirements WHERE id = ?", (req_id,))


# ------------------------------------------------------------------------------ portals
def list_enabled_portals() -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in
                conn.execute("SELECT * FROM portals WHERE enabled = 1 ORDER BY name")]


def update_portal_last_run(portal_id) -> None:
    with connect() as conn:
        conn.execute("UPDATE portals SET last_run_at = ? WHERE id = ?",
                     (_now(), portal_id))


# -------------------------------------------------------------- raw staging boundary D12
def add_raw(portal_id, url, raw_html) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO raw_listings (portal_id, url, raw_html, fetched_at, "
            "parse_status) VALUES (?, ?, ?, ?, 'pending')",
            (portal_id, url, raw_html, _now()),
        )
        return cur.lastrowid


def pending_raw() -> list[dict]:
    """Pending raw rows joined with portal name (parsers are keyed by portal name)."""
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT r.*, p.name AS portal_name FROM raw_listings r "
            "JOIN portals p ON p.id = r.portal_id WHERE r.parse_status = 'pending' "
            "ORDER BY r.id")]


def mark_raw_parsed(raw_id) -> None:
    with connect() as conn:
        conn.execute("UPDATE raw_listings SET parse_status = 'parsed', parse_error = "
                     "NULL WHERE id = ?", (raw_id,))


def mark_raw_error(raw_id, msg) -> None:
    with connect() as conn:
        conn.execute("UPDATE raw_listings SET parse_status = 'error', parse_error = ? "
                     "WHERE id = ?", (str(msg), raw_id))


def reset_raw_pending(portal_id) -> int:
    """Replay a site after a selector fix: flip its raw rows back to pending (D12)."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE raw_listings SET parse_status = 'pending', parse_error = NULL "
            "WHERE portal_id = ?", (portal_id,))
        return cur.rowcount


# ----------------------------------------------------------------------------- listings
def upsert_listing(listing: dict) -> int:
    """Insert or, if the fingerprint already exists, bump last_seen_at (un-stale it).
    Required keys: portal_id, url, title, price, size_sqm, sector. Optional:
    external_id, raw_location, posted_date. Computes the fingerprint (D7)."""
    fp = fingerprint(listing.get("price"), listing.get("size_sqm"),
                     listing.get("sector"), listing.get("title"))
    now = _now()
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM listings WHERE fingerprint = ?", (fp,)).fetchone()
        if existing:
            conn.execute("UPDATE listings SET last_seen_at = ?, is_stale = 0, "
                         "price = ?, url = ?, image_url = ?, advertiser = ?, "
                         "ownership = ?, approving_authority = ?, description = ? "
                         "WHERE id = ?",
                         (now, listing.get("price"), listing.get("url"),
                          listing.get("image_url"), listing.get("advertiser"),
                          listing.get("ownership"), listing.get("approving_authority"),
                          listing.get("description"), existing["id"]))
            return existing["id"]
        cur = conn.execute(
            "INSERT INTO listings (portal_id, external_id, url, title, price, size_sqm, "
            "sector, raw_location, posted_date, image_url, advertiser, ownership, "
            "approving_authority, description, fingerprint, first_seen_at, last_seen_at, "
            "is_stale) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (listing["portal_id"], listing.get("external_id"), listing.get("url"),
             listing.get("title"), listing.get("price"), listing.get("size_sqm"),
             listing.get("sector"), listing.get("raw_location"),
             listing.get("posted_date"), listing.get("image_url"),
             listing.get("advertiser"), listing.get("ownership"),
             listing.get("approving_authority"), listing.get("description"),
             fp, now, now),
        )
        return cur.lastrowid


def list_active_listings() -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in
                conn.execute("SELECT * FROM listings WHERE is_stale = 0")]


def is_noida_authority(listing: dict) -> bool:
    """True if a listing is a NOIDA-Authority, non-freehold property (D21).
    Used to keep only authority sectors/plots out of freehold private colonies."""
    auth = str(listing.get("approving_authority") or "").strip().upper()
    ownership = str(listing.get("ownership") or "").strip().lower()
    return auth == "NOIDA" and ownership != "freehold"


def mark_stale(threshold_runs=3) -> int:
    """Mark listings not seen within threshold_runs * HOURS_PER_RUN hours as stale (Q3)."""
    cutoff = (datetime.now(timezone.utc)
              - timedelta(hours=threshold_runs * HOURS_PER_RUN)).isoformat()
    with connect() as conn:
        cur = conn.execute(
            "UPDATE listings SET is_stale = 1 WHERE last_seen_at < ? AND is_stale = 0",
            (cutoff,))
        return cur.rowcount


# ------------------------------------------------------------------------------ matches
def record_match(req_id, listing_id, score) -> None:
    """Insert a match; ignore if (requirement, listing) already recorded (UNIQUE)."""
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO matches (requirement_id, listing_id, score, "
            "notified, created_at) VALUES (?, ?, ?, 0, ?)",
            (req_id, listing_id, score, _now()))


def unnotified_matches() -> list[dict]:
    """Un-notified matches joined with listing fields for the notifier (D6)."""
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT m.id AS match_id, m.requirement_id, m.score, l.*, "
            "req.owner AS owner FROM matches m "
            "JOIN listings l ON l.id = m.listing_id "
            "JOIN requirements req ON req.id = m.requirement_id "
            "WHERE m.notified = 0 ORDER BY m.score DESC")]


def mark_notified(match_id) -> None:
    with connect() as conn:
        conn.execute("UPDATE matches SET notified = 1 WHERE id = ?", (match_id,))


# ----------------------------------------------------------------- shortlist / feedback
def set_feedback(listing_id, verdict, reason=None) -> None:
    """Record a like/dislike for a listing, optionally with a pass reason (D29).
    verdict must be 'like' or 'nope'. Toggle rules:
      • Like / Pass button (reason=None): clicking the active verdict again clears it.
      • A pass-reason chip (verdict='nope', reason set): sets the reason; re-clicking the
        same reason clears just the reason (the listing stays passed)."""
    if verdict not in ("like", "nope"):
        return
    with connect() as conn:
        row = conn.execute("SELECT verdict, reason FROM feedback WHERE listing_id = ?",
                           (listing_id,)).fetchone()
        if verdict == "nope" and reason is not None:
            # reason chip: keep the pass, set/toggle the reason
            new_reason = None if (row and row["reason"] == reason) else reason
            conn.execute(
                "INSERT INTO feedback (listing_id, verdict, reason, updated_at) "
                "VALUES (?, 'nope', ?, ?) ON CONFLICT(listing_id) DO UPDATE SET "
                "verdict = 'nope', reason = excluded.reason, updated_at = excluded.updated_at",
                (listing_id, new_reason, _now()))
        elif row and row["verdict"] == verdict:  # same Like/Pass again -> un-set (toggle)
            conn.execute("DELETE FROM feedback WHERE listing_id = ?", (listing_id,))
        else:
            conn.execute(
                "INSERT INTO feedback (listing_id, verdict, reason, updated_at) "
                "VALUES (?, ?, NULL, ?) ON CONFLICT(listing_id) DO UPDATE SET "
                "verdict = excluded.verdict, reason = NULL, updated_at = excluded.updated_at",
                (listing_id, verdict, _now()))


def feedback_map() -> dict:
    """{listing_id: 'like'|'nope'} for all rated listings."""
    with connect() as conn:
        return {r["listing_id"]: r["verdict"]
                for r in conn.execute("SELECT listing_id, verdict FROM feedback")}


def feedback_reasons() -> dict:
    """{listing_id: reason} for passed listings that have a reason set (D29)."""
    with connect() as conn:
        return {r["listing_id"]: r["reason"] for r in conn.execute(
            "SELECT listing_id, reason FROM feedback WHERE reason IS NOT NULL")}


def list_feedback(verdict) -> list[dict]:
    """Listings the user gave `verdict` to, newest first, joined with listing fields."""
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT l.*, f.verdict AS verdict, f.reason AS pass_reason, "
            "f.updated_at AS rated_at FROM feedback f "
            "JOIN listings l ON l.id = f.listing_id "
            "WHERE f.verdict = ? ORDER BY f.updated_at DESC", (verdict,))]


# ------------------------------------------------------------- follow-up tracking (D29)
def _track_upsert(conn, listing_id, **fields) -> None:
    """Upsert a tracking row, updating only the given column(s)."""
    cols = ", ".join(f"{k} = excluded.{k}" for k in fields)
    keys = ", ".join(fields)
    qs = ", ".join("?" for _ in fields)
    conn.execute(
        f"INSERT INTO tracking (listing_id, {keys}, updated_at) VALUES (?, {qs}, ?) "
        f"ON CONFLICT(listing_id) DO UPDATE SET {cols}, updated_at = excluded.updated_at",
        (listing_id, *fields.values(), _now()))


def set_contacted(listing_id, contacted: bool | None = None) -> None:
    """Mark a listing contacted (stamps the time) or not. contacted=None toggles."""
    with connect() as conn:
        row = conn.execute("SELECT contacted_at FROM tracking WHERE listing_id = ?",
                           (listing_id,)).fetchone()
        if contacted is None:  # toggle
            contacted = not (row and row["contacted_at"])
        _track_upsert(conn, listing_id, contacted_at=_now() if contacted else None)


def set_note(listing_id, notes) -> None:
    """Save free-text follow-up notes for a listing (empty string clears)."""
    with connect() as conn:
        _track_upsert(conn, listing_id, notes=(notes or "").strip() or None)


def tracking_map() -> dict:
    """{listing_id: {'contacted_at': str|None, 'notes': str|None}} for tracked listings."""
    with connect() as conn:
        return {r["listing_id"]: {"contacted_at": r["contacted_at"], "notes": r["notes"]}
                for r in conn.execute(
                    "SELECT listing_id, contacted_at, notes FROM tracking")}


def list_contacted() -> list[dict]:
    """Listings marked contacted, most recent first, joined with listing fields."""
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT l.*, t.contacted_at AS contacted_at, t.notes AS notes "
            "FROM tracking t JOIN listings l ON l.id = t.listing_id "
            "WHERE t.contacted_at IS NOT NULL ORDER BY t.contacted_at DESC")]


# ------------------------------------------------------------------ observability (D15)
def start_run() -> int:
    with connect() as conn:
        cur = conn.execute("INSERT INTO runs (started_at) VALUES (?)", (_now(),))
        return cur.lastrowid


def finish_run(run_id, **counts) -> None:
    """counts: portals_run, raw_fetched, parsed_ok, parse_errors, new_matches,
    notified, error."""
    allowed = ("portals_run", "raw_fetched", "parsed_ok", "parse_errors",
               "new_matches", "notified", "error")
    fields = {k: v for k, v in counts.items() if k in allowed}
    sets = ", ".join(f"{k} = ?" for k in fields)
    sets = f"finished_at = ?{', ' + sets if sets else ''}"
    with connect() as conn:
        conn.execute(f"UPDATE runs SET {sets} WHERE id = ?",
                     (_now(), *fields.values(), run_id))


# ------------------------------------------------------------------- settings (D17)
def get_setting(key, default=None) -> float | None:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key, value) -> None:
    """Upsert a tuning knob. Editable live from the Streamlit Settings page (D17)."""
    with connect() as conn:
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                     (key, float(value)))


def all_settings() -> dict:
    """All knobs as a dict, with seeded defaults filled in for any missing key."""
    with connect() as conn:
        rows = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}
    return {**SEED_SETTINGS, **rows}


def matcher_config() -> dict:
    """The subset of settings the matcher consumes (pass to matcher.matches_for)."""
    s = all_settings()
    return {k: s[k] for k in ("threshold", "w_size", "w_price", "w_sector",
                              "budget_softcap_pct", "sector_miss_fit", "type_miss_fit")}


def recent_runs(limit=20) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))]


def status_summary() -> dict:
    """Snapshot for the System page (D15): per-portal info + pipeline-health counts."""
    with connect() as conn:
        portals = [dict(r) for r in conn.execute(
            "SELECT id, name, enabled, last_run_at FROM portals ORDER BY name")]
        raw_health = {r["parse_status"]: r["n"] for r in conn.execute(
            "SELECT parse_status, COUNT(*) AS n FROM raw_listings GROUP BY parse_status")}
        recent_errors = [dict(r) for r in conn.execute(
            "SELECT id, portal_id, url, parse_error FROM raw_listings "
            "WHERE parse_status = 'error' ORDER BY id DESC LIMIT 20")]
        totals = dict(conn.execute(
            "SELECT (SELECT COUNT(*) FROM listings WHERE is_stale = 0) AS active_listings, "
            "(SELECT COUNT(*) FROM listings WHERE is_stale = 1) AS stale_listings, "
            "(SELECT COUNT(*) FROM matches) AS total_matches, "
            "(SELECT COUNT(*) FROM matches WHERE notified = 0) AS unnotified_matches"
        ).fetchone())
    return {"portals": portals, "raw_health": raw_health,
            "recent_errors": recent_errors, "totals": totals}


if __name__ == "__main__":
    init()
    print(f"Initialized {DB_PATH}")
    print(f"Seeded portals: {[p['name'] for p in list_enabled_portals()]}")
