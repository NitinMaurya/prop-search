"""Supabase (Postgres) data access for the scraper node.

Connects directly to the Supabase Postgres via DATABASE_URL (the postgres role bypasses
RLS — the scraper is trusted infra). Mirrors the v1 db.py functions the pipeline needs,
ported to Postgres. The API has its own data layer; this one only does what a scrape run
requires: read requirements/settings, upsert listings, record matches, runs, notify.
"""

import hashlib
import re

import psycopg
from psycopg.rows import dict_row

# Settings the matcher consumes (D17). Cast to float on read.
_MATCHER_KEYS = ("threshold", "w_size", "w_price", "w_sector",
                 "budget_softcap_pct", "sector_miss_fit", "type_miss_fit")


def fingerprint(price, size_sqm, sector, title) -> str:
    """Dedup key (D7): normalized price + size + sector + fuzzy title."""
    price_bucket = round((price or 0) / 100000)          # nearest lakh
    size_bucket = round((size_sqm or 0))                 # nearest sqm
    sector_norm = re.sub(r"\s+", " ", (sector or "").strip().lower())
    title_tokens = sorted(re.findall(r"[a-z0-9]+", (title or "").lower()))
    basis = f"{price_bucket}|{size_bucket}|{sector_norm}|{' '.join(title_tokens)}"
    return hashlib.sha1(basis.encode()).hexdigest()


class Store:
    """Thin Postgres data layer for one scrape run. Autocommit; one connection per run."""

    def __init__(self, dsn: str):
        self.conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)

    def close(self):
        self.conn.close()

    # --------------------------------------------------------------- reads
    def active_requirements(self) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM requirements WHERE active = true")
            return cur.fetchall()

    def enabled_portals(self, only: str | None = None) -> list[dict]:
        q = "SELECT * FROM portals WHERE enabled = true"
        params: tuple = ()
        if only:
            q += " AND lower(name) = lower(%s)"
            params = (only,)
        with self.conn.cursor() as cur:
            cur.execute(q, params)
            return cur.fetchall()

    def settings(self) -> dict:
        with self.conn.cursor() as cur:
            cur.execute("SELECT key, value FROM settings")
            return {r["key"]: r["value"] for r in cur.fetchall()}

    def setting(self, key: str, default=None):
        return self.settings().get(key, default)

    def matcher_config(self) -> dict:
        s = self.settings()
        out = {}
        for k in _MATCHER_KEYS:
            if k in s:
                try:
                    out[k] = float(s[k])
                except (TypeError, ValueError):
                    pass
        return out

    def active_listings(self) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM listings WHERE is_stale = false")
            return cur.fetchall()

    def unnotified_matches(self) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT m.id AS match_id, m.requirement_id, m.score, l.*, "
                "r.owner AS owner FROM matches m "
                "JOIN listings l ON l.id = m.listing_id "
                "JOIN requirements r ON r.id = m.requirement_id "
                "WHERE m.notified = false ORDER BY m.score DESC")
            return cur.fetchall()

    # --------------------------------------------------------------- writes
    def upsert_listing(self, listing: dict) -> int:
        """Insert or, on fingerprint match, refresh + un-stale. Returns the listing id."""
        fp = fingerprint(listing.get("price"), listing.get("size_sqm"),
                         listing.get("sector"), listing.get("title"))
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO listings (portal_id, external_id, url, title, price, "
                "size_sqm, sector, raw_location, posted_date, image_url, advertiser, "
                "ownership, approving_authority, description, fingerprint, "
                "first_seen_at, last_seen_at, is_stale) "
                "VALUES (%(portal_id)s, %(external_id)s, %(url)s, %(title)s, %(price)s, "
                "%(size_sqm)s, %(sector)s, %(raw_location)s, %(posted_date)s, "
                "%(image_url)s, %(advertiser)s, %(ownership)s, %(approving_authority)s, "
                "%(description)s, %(fp)s, now(), now(), false) "
                "ON CONFLICT (fingerprint) DO UPDATE SET "
                "last_seen_at = now(), is_stale = false, price = excluded.price, "
                "url = excluded.url, image_url = excluded.image_url, "
                "advertiser = excluded.advertiser, ownership = excluded.ownership, "
                "approving_authority = excluded.approving_authority, "
                "description = excluded.description "
                "RETURNING id",
                {"portal_id": listing["portal_id"],
                 "external_id": listing.get("external_id"),
                 "url": listing.get("url"), "title": listing.get("title"),
                 "price": listing.get("price"), "size_sqm": listing.get("size_sqm"),
                 "sector": listing.get("sector"),
                 "raw_location": listing.get("raw_location"),
                 "posted_date": listing.get("posted_date"),
                 "image_url": listing.get("image_url"),
                 "advertiser": listing.get("advertiser"),
                 "ownership": listing.get("ownership"),
                 "approving_authority": listing.get("approving_authority"),
                 "description": listing.get("description"), "fp": fp})
            return cur.fetchone()["id"]

    def record_match(self, req_id: int, listing_id: int, score: float) -> bool:
        """Upsert a match; returns True if it was newly inserted (xmax = 0)."""
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO matches (requirement_id, listing_id, score) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (requirement_id, listing_id) DO UPDATE "
                "SET score = excluded.score "
                "RETURNING (xmax = 0) AS inserted",
                (req_id, listing_id, score))
            return bool(cur.fetchone()["inserted"])

    def mark_stale(self, threshold_runs: int = 3, hours_per_run: int = 6) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE listings SET is_stale = true "
                "WHERE is_stale = false "
                "AND last_seen_at < now() - make_interval(hours => %s)",
                (threshold_runs * hours_per_run,))
            return cur.rowcount

    def mark_notified(self, match_id: int) -> None:
        with self.conn.cursor() as cur:
            cur.execute("UPDATE matches SET notified = true WHERE id = %s", (match_id,))

    def update_portal_last_run(self, portal_id: int) -> None:
        with self.conn.cursor() as cur:
            cur.execute("UPDATE portals SET last_run_at = now() WHERE id = %s",
                        (portal_id,))

    # --------------------------------------------------------------- runs
    def start_run(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO runs (started_at) VALUES (now()) RETURNING id")
            return cur.fetchone()["id"]

    def finish_run(self, run_id: int, error: str | None = None, **counts) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE runs SET finished_at = now(), raw_fetched = %s, parsed_ok = %s, "
                "parse_errors = %s, new_matches = %s, notified = %s, error = %s "
                "WHERE id = %s",
                (counts.get("raw_fetched", 0), counts.get("parsed_ok", 0),
                 counts.get("parse_errors", 0), counts.get("new_matches", 0),
                 counts.get("notified", 0), error, run_id))
