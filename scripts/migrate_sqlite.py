"""One-shot, idempotent migration of the v1 SQLite DB → Supabase (v2).

Global tables (listings, settings, runs) migrate immediately. Per-user tables
(requirements, matches, feedback, tracking) migrate to the single auth user — so log
into the web app once first; otherwise those are skipped (re-run later to finish).

Listing ids change (new identity PKs), so matches/feedback/tracking are remapped by
listing fingerprint. Safe to re-run: listings upsert on fingerprint; matches/feedback/
tracking upsert on their keys; requirements skip if an identical one exists; runs only
seed when the v2 runs table is empty.

Usage (from the v2 worktree, DATABASE_URL in env):
    SQLITE_DB=../prop-search/data/prop_search.db \
    apps/api/.venv/bin/python scripts/migrate_sqlite.py
"""

import json
import os
import sqlite3
import sys

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQLITE_DB = os.environ.get(
    "SQLITE_DB", os.path.join(HERE, "..", "prop-search", "data", "prop_search.db"))


def _jlist(v):
    if isinstance(v, list):
        return v
    try:
        out = json.loads(v) if v else []
        return out if isinstance(out, list) else []
    except (ValueError, TypeError):
        return []


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        sys.exit("DATABASE_URL not set (source apps/api/.env.local first).")
    if not os.path.exists(SQLITE_DB):
        sys.exit(f"SQLite DB not found at {SQLITE_DB} (set SQLITE_DB).")

    lite = sqlite3.connect(SQLITE_DB)
    lite.row_factory = sqlite3.Row

    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as conn, conn.cursor() as cur:
        # ---- portal id remap (by name) -------------------------------------------
        v1_portal = {r["id"]: r["name"] for r in lite.execute("SELECT id, name FROM portals")}
        cur.execute("SELECT id, name FROM portals")
        v2_portal = {r["name"]: r["id"] for r in cur.fetchall()}

        # ---- listings (global) ---------------------------------------------------
        listing_map: dict[int, int] = {}  # v1 id -> v2 id
        cols = ("external_id url title price size_sqm sector raw_location posted_date "
                "image_url advertiser ownership approving_authority description "
                "fingerprint first_seen_at last_seen_at is_stale").split()
        n_listings = 0
        for raw in lite.execute("SELECT * FROM listings"):
            r = dict(raw)
            pid = v2_portal.get(v1_portal.get(r.get("portal_id")))
            if not pid:
                continue
            vals = {c: r.get(c) for c in cols}
            vals["is_stale"] = bool(r.get("is_stale"))
            cur.execute(
                "INSERT INTO listings (portal_id, external_id, url, title, price, size_sqm, "
                "sector, raw_location, posted_date, image_url, advertiser, ownership, "
                "approving_authority, description, fingerprint, first_seen_at, last_seen_at, "
                "is_stale) VALUES (%(pid)s, %(external_id)s, %(url)s, %(title)s, %(price)s, "
                "%(size_sqm)s, %(sector)s, %(raw_location)s, %(posted_date)s, %(image_url)s, "
                "%(advertiser)s, %(ownership)s, %(approving_authority)s, %(description)s, "
                "%(fingerprint)s, %(first_seen_at)s, %(last_seen_at)s, %(is_stale)s) "
                "ON CONFLICT (fingerprint) DO UPDATE SET last_seen_at = excluded.last_seen_at "
                "RETURNING id", {**vals, "pid": pid})
            listing_map[r["id"]] = cur.fetchone()["id"]
            n_listings += 1
        print(f"listings: {n_listings} migrated")

        # ---- settings (global, upsert values) ------------------------------------
        for r in lite.execute("SELECT key, value FROM settings"):
            cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) "
                        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                        (r["key"], r["value"]))
        print("settings: synced")

        # ---- runs (global, only if v2 empty) -------------------------------------
        cur.execute("SELECT count(*) AS n FROM runs")
        if cur.fetchone()["n"] == 0:
            n_runs = 0
            for r in lite.execute("SELECT * FROM runs"):
                d = dict(r)
                cur.execute(
                    "INSERT INTO runs (started_at, finished_at, raw_fetched, parsed_ok, "
                    "parse_errors, new_matches, notified) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (d.get("started_at"), d.get("finished_at"), d.get("raw_fetched"),
                     d.get("parsed_ok"), d.get("parse_errors"), d.get("new_matches"),
                     d.get("notified")))
                n_runs += 1
            print(f"runs: {n_runs} migrated")
        else:
            print("runs: skipped (v2 already has runs)")

        # ---- resolve user for per-user tables ------------------------------------
        forced = os.environ.get("IMPORT_USER_ID")
        cur.execute("SELECT id, email FROM auth.users ORDER BY created_at")
        users = cur.fetchall()
        if forced:
            uid = forced
        elif len(users) == 1:
            uid = users[0]["id"]
        elif not users:
            print("\n⚠️  No auth user yet — global tables done. Log into the web app "
                  "once, then re-run this script to migrate requirements/matches/"
                  "feedback/tracking.")
            return 0
        else:
            sys.exit("Multiple users; set IMPORT_USER_ID to one of: "
                     + ", ".join(f"{u['email']} ({u['id']})" for u in users))
        print(f"user: {uid}")

        # ---- requirements (per-user) ---------------------------------------------
        req_map: dict[int, int] = {}
        for raw in lite.execute("SELECT * FROM requirements"):
            r = dict(raw)
            cur.execute(
                "SELECT id FROM requirements WHERE user_id=%s AND owner IS NOT DISTINCT "
                "FROM %s AND property_type=%s AND budget_min IS NOT DISTINCT FROM %s AND "
                "budget_max IS NOT DISTINCT FROM %s",
                (uid, r.get("owner"), r["property_type"], r.get("budget_min"), r.get("budget_max")))
            existing = cur.fetchone()
            if existing:
                req_map[r["id"]] = existing["id"]
                continue
            cur.execute(
                "INSERT INTO requirements (user_id, owner, property_type, sizes_sqm, "
                "size_tolerance_pct, budget_min, budget_max, sectors, active) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (uid, r.get("owner"), r["property_type"], Jsonb(_jlist(r.get("sizes_sqm"))),
                 r.get("size_tolerance_pct"), r.get("budget_min"), r.get("budget_max"),
                 Jsonb(_jlist(r.get("sectors"))), bool(r.get("active"))))
            req_map[r["id"]] = cur.fetchone()["id"]
        print(f"requirements: {len(req_map)} mapped")

        # ---- matches (per-user, remapped) ----------------------------------------
        n_m = 0
        for raw in lite.execute("SELECT * FROM matches"):
            r = dict(raw)
            nr, nl = req_map.get(r["requirement_id"]), listing_map.get(r["listing_id"])
            if not nr or not nl:
                continue
            cur.execute(
                "INSERT INTO matches (requirement_id, listing_id, score, notified) "
                "VALUES (%s,%s,%s,%s) ON CONFLICT (requirement_id, listing_id) "
                "DO UPDATE SET score = excluded.score",
                (nr, nl, r.get("score"), bool(r.get("notified"))))
            n_m += 1
        print(f"matches: {n_m} migrated")

        # ---- feedback (per-user, remapped) ---------------------------------------
        n_f = 0
        for raw in lite.execute("SELECT * FROM feedback"):
            r = dict(raw)
            nl = listing_map.get(r["listing_id"])
            if not nl:
                continue
            cur.execute(
                "INSERT INTO feedback (user_id, listing_id, verdict, reason, updated_at) "
                "VALUES (%s,%s,%s,%s, now()) ON CONFLICT (user_id, listing_id) DO UPDATE "
                "SET verdict = excluded.verdict, reason = excluded.reason",
                (uid, nl, r["verdict"], r.get("reason")))
            n_f += 1
        print(f"feedback: {n_f} migrated")

        # ---- tracking (per-user, remapped) ---------------------------------------
        n_t = 0
        for raw in lite.execute("SELECT * FROM tracking"):
            r = dict(raw)
            nl = listing_map.get(r["listing_id"])
            if not nl:
                continue
            cur.execute(
                "INSERT INTO tracking (user_id, listing_id, contacted_at, notes, updated_at) "
                "VALUES (%s,%s,%s,%s, now()) ON CONFLICT (user_id, listing_id) DO UPDATE "
                "SET contacted_at = excluded.contacted_at, notes = excluded.notes",
                (uid, nl, r.get("contacted_at"), r.get("notes")))
            n_t += 1
        print(f"tracking: {n_t} migrated")

    lite.close()
    print("✅ migration complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
