"""Data access for the API. Connects to Supabase Postgres as the postgres role
(bypasses RLS); every user-scoped query passes the authenticated user_id explicitly.
"""

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from . import cache
from .config import settings

# TTLs (seconds). Matches is invalidated on the user's own writes, so it can be longer;
# the bound only matters for cross-process changes (a scrape's new matches).
MATCHES_TTL = 90
SETTINGS_TTL = 300
SYSTEM_TTL = 30

_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            settings.database_url, open=True, min_size=1, max_size=5,
            kwargs={"row_factory": dict_row})
    return _pool


# ----------------------------------------------------------------- requirements
def list_requirements(uid: str) -> list[dict]:
    with pool().connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM requirements WHERE user_id = %s "
                    "ORDER BY created_at DESC", (uid,))
        return cur.fetchall()


def create_requirement(uid: str, r: dict) -> dict:
    with pool().connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO requirements (user_id, owner, property_type, sizes_sqm, "
            "size_tolerance_pct, budget_min, budget_max, sectors, active) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
            (uid, r.get("owner"), r["property_type"], Jsonb(r["sizes_sqm"]),
             r["size_tolerance_pct"], r.get("budget_min"), r.get("budget_max"),
             Jsonb(r["sectors"]), r.get("active", True)))
        row = cur.fetchone()
    invalidate_matches(uid)
    return row


def update_requirement(uid: str, req_id: int, r: dict) -> dict | None:
    with pool().connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE requirements SET owner = %s, property_type = %s, sizes_sqm = %s, "
            "size_tolerance_pct = %s, budget_min = %s, budget_max = %s, sectors = %s, "
            "active = %s WHERE id = %s AND user_id = %s RETURNING *",
            (r.get("owner"), r["property_type"], Jsonb(r["sizes_sqm"]),
             r["size_tolerance_pct"], r.get("budget_min"), r.get("budget_max"),
             Jsonb(r["sectors"]), r.get("active", True), req_id, uid))
        row = cur.fetchone()
    invalidate_matches(uid)
    return row


def delete_requirement(uid: str, req_id: int) -> bool:
    with pool().connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM requirements WHERE id = %s AND user_id = %s",
                    (req_id, uid))
        ok = cur.rowcount > 0
    invalidate_matches(uid)
    return ok


# ----------------------------------------------------------------- matches
def _matches_key(uid: str) -> str:
    return f"matches:{uid}"


def invalidate_matches(uid: str) -> None:
    cache.invalidate(_matches_key(uid))


def list_matches(uid: str) -> list[dict]:
    """The user's matches, enriched with listing fields + their feedback/tracking.

    Cached per user (TTL); invalidated on that user's feedback/tracking/requirement
    writes. Single round-trip: the NOIDA-authority filter and is_new flag are folded
    into SQL via subqueries, so a cache miss is still one DB hop."""
    cached = cache.get(_matches_key(uid))
    if cached is not None:
        return cached
    with pool().connection() as conn, conn.cursor() as cur:
        cur.execute(
            "WITH cfg AS (SELECT value FROM settings WHERE key = 'noida_authority_only'), "
            "last_run AS (SELECT max(started_at) AS ts FROM runs) "
            "SELECT m.id AS match_id, m.requirement_id, m.score, l.*, "
            "r.owner AS owner, f.verdict AS verdict, f.reason AS pass_reason, "
            "t.contacted_at AS contacted_at, t.notes AS notes, "
            "(l.first_seen_at >= (SELECT ts FROM last_run)) AS is_new "
            "FROM matches m "
            "JOIN requirements r ON r.id = m.requirement_id AND r.user_id = %(uid)s "
            "JOIN listings l ON l.id = m.listing_id "
            "LEFT JOIN feedback f ON f.listing_id = l.id AND f.user_id = %(uid)s "
            "LEFT JOIN tracking t ON t.listing_id = l.id AND t.user_id = %(uid)s "
            "WHERE coalesce((SELECT value FROM cfg), '0') NOT IN ('1','true','yes','on') "
            "   OR (upper(coalesce(l.approving_authority,'')) = 'NOIDA' "
            "       AND lower(coalesce(l.ownership,'')) <> 'freehold') "
            "ORDER BY m.score DESC NULLS LAST",
            {"uid": uid})
        rows = cur.fetchall()
    cache.put(_matches_key(uid), rows, MATCHES_TTL)
    return rows


# ----------------------------------------------------------------- feedback (D29)
def set_feedback(uid: str, listing_id: int, verdict: str, reason: str | None) -> None:
    with pool().connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT verdict, reason FROM feedback "
                    "WHERE user_id = %s AND listing_id = %s", (uid, listing_id))
        row = cur.fetchone()
        if verdict == "nope" and reason is not None:
            new_reason = None if (row and row["reason"] == reason) else reason
            cur.execute(
                "INSERT INTO feedback (user_id, listing_id, verdict, reason, updated_at) "
                "VALUES (%s, %s, 'nope', %s, now()) "
                "ON CONFLICT (user_id, listing_id) DO UPDATE SET verdict = 'nope', "
                "reason = excluded.reason, updated_at = now()",
                (uid, listing_id, new_reason))
        elif row and row["verdict"] == verdict:
            cur.execute("DELETE FROM feedback WHERE user_id = %s AND listing_id = %s",
                        (uid, listing_id))
        else:
            cur.execute(
                "INSERT INTO feedback (user_id, listing_id, verdict, reason, updated_at) "
                "VALUES (%s, %s, %s, NULL, now()) "
                "ON CONFLICT (user_id, listing_id) DO UPDATE SET verdict = excluded.verdict, "
                "reason = NULL, updated_at = now()",
                (uid, listing_id, verdict))
    invalidate_matches(uid)


# ----------------------------------------------------------------- tracking (D29)
def set_contacted(uid: str, listing_id: int) -> bool:
    """Toggle contacted; returns the new contacted state."""
    with pool().connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT contacted_at FROM tracking "
                    "WHERE user_id = %s AND listing_id = %s", (uid, listing_id))
        row = cur.fetchone()
        now_contacted = not (row and row["contacted_at"])
        cur.execute(
            "INSERT INTO tracking (user_id, listing_id, contacted_at, updated_at) "
            "VALUES (%s, %s, CASE WHEN %s THEN now() ELSE NULL END, now()) "
            "ON CONFLICT (user_id, listing_id) DO UPDATE SET "
            "contacted_at = excluded.contacted_at, updated_at = now()",
            (uid, listing_id, now_contacted))
    invalidate_matches(uid)
    return now_contacted


def set_note(uid: str, listing_id: int, notes: str | None) -> None:
    clean = (notes or "").strip() or None
    with pool().connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tracking (user_id, listing_id, notes, updated_at) "
            "VALUES (%s, %s, %s, now()) "
            "ON CONFLICT (user_id, listing_id) DO UPDATE SET notes = excluded.notes, "
            "updated_at = now()",
            (uid, listing_id, clean))
    invalidate_matches(uid)


# ----------------------------------------------------------------- settings (global)
def get_settings() -> dict:
    cached = cache.get("settings")
    if cached is not None:
        return cached
    with pool().connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT key, value FROM settings")
        out = {r["key"]: r["value"] for r in cur.fetchall()}
    cache.put("settings", out, SETTINGS_TTL)
    return out


def update_settings(values: dict) -> dict:
    with pool().connection() as conn, conn.cursor() as cur:
        for k, v in values.items():
            cur.execute(
                "INSERT INTO settings (key, value) VALUES (%s, %s) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (k, str(v)))
    cache.invalidate("settings")
    return get_settings()


# ----------------------------------------------------------------- system (global)
def system_status() -> dict:
    cached = cache.get("system")
    if cached is not None:
        return cached
    with pool().connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FILTER (WHERE not is_stale) AS active, "
                    "count(*) FILTER (WHERE is_stale) AS stale FROM listings")
        totals = cur.fetchone()
        cur.execute("SELECT * FROM portals ORDER BY name")
        portals = cur.fetchall()
        cur.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT 20")
        runs = cur.fetchall()
    result = {"totals": totals, "portals": portals, "runs": runs}
    cache.put("system", result, SYSTEM_TTL)
    return result
