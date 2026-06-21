"""Data access for the API. Connects to Supabase Postgres as the postgres role
(bypasses RLS); every user-scoped query passes the authenticated user_id explicitly.
"""

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .config import settings

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
        return cur.fetchone()


def update_requirement(uid: str, req_id: int, r: dict) -> dict | None:
    with pool().connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE requirements SET owner = %s, property_type = %s, sizes_sqm = %s, "
            "size_tolerance_pct = %s, budget_min = %s, budget_max = %s, sectors = %s, "
            "active = %s WHERE id = %s AND user_id = %s RETURNING *",
            (r.get("owner"), r["property_type"], Jsonb(r["sizes_sqm"]),
             r["size_tolerance_pct"], r.get("budget_min"), r.get("budget_max"),
             Jsonb(r["sectors"]), r.get("active", True), req_id, uid))
        return cur.fetchone()


def delete_requirement(uid: str, req_id: int) -> bool:
    with pool().connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM requirements WHERE id = %s AND user_id = %s",
                    (req_id, uid))
        return cur.rowcount > 0


# ----------------------------------------------------------------- matches
def list_matches(uid: str) -> list[dict]:
    """The user's matches, enriched with listing fields + their feedback/tracking."""
    with pool().connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT m.id AS match_id, m.requirement_id, m.score, l.*, "
            "r.owner AS owner, f.verdict AS verdict, f.reason AS pass_reason, "
            "t.contacted_at AS contacted_at, t.notes AS notes "
            "FROM matches m "
            "JOIN requirements r ON r.id = m.requirement_id AND r.user_id = %(uid)s "
            "JOIN listings l ON l.id = m.listing_id "
            "LEFT JOIN feedback f ON f.listing_id = l.id AND f.user_id = %(uid)s "
            "LEFT JOIN tracking t ON t.listing_id = l.id AND t.user_id = %(uid)s "
            "ORDER BY m.score DESC NULLS LAST",
            {"uid": uid})
        return cur.fetchall()


def latest_run_start() -> str | None:
    with pool().connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT started_at FROM runs ORDER BY started_at DESC LIMIT 1")
        row = cur.fetchone()
        return row["started_at"].isoformat() if row and row["started_at"] else None


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


# ----------------------------------------------------------------- settings (global)
def get_settings() -> dict:
    with pool().connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT key, value FROM settings")
        return {r["key"]: r["value"] for r in cur.fetchall()}


def update_settings(values: dict) -> dict:
    with pool().connection() as conn, conn.cursor() as cur:
        for k, v in values.items():
            cur.execute(
                "INSERT INTO settings (key, value) VALUES (%s, %s) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (k, str(v)))
    return get_settings()


# ----------------------------------------------------------------- system (global)
def system_status() -> dict:
    with pool().connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FILTER (WHERE not is_stale) AS active, "
                    "count(*) FILTER (WHERE is_stale) AS stale FROM listings")
        totals = cur.fetchone()
        cur.execute("SELECT * FROM portals ORDER BY name")
        portals = cur.fetchall()
        cur.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT 20")
        runs = cur.fetchall()
    return {"totals": totals, "portals": portals, "runs": runs}
