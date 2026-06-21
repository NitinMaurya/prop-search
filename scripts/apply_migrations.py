"""Apply the SQL migrations in supabase/migrations/ to the database in DATABASE_URL.

Run order is lexical (0001, 0002, …). Each file runs in its own transaction. Idempotent
files (seeds use ON CONFLICT) are safe to re-run. Never prints the connection string.

Usage:
    set -a; source apps/api/.env; set +a        # load DATABASE_URL (not echoed)
    apps/api/.venv/bin/python scripts/apply_migrations.py
"""

import glob
import os
import sys

import psycopg

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS = sorted(glob.glob(os.path.join(HERE, "supabase", "migrations", "*.sql")))


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set. Do:  set -a; source apps/api/.env; set +a")
        return 2
    if not MIGRATIONS:
        print("No migration files found under supabase/migrations/")
        return 2

    # Connect WITHOUT echoing the dsn.
    try:
        conn = psycopg.connect(dsn, autocommit=False)
    except Exception as e:  # noqa: BLE001
        print(f"Could not connect: {type(e).__name__}: {e}")
        print("Tip: if the direct db.<ref>.supabase.co host fails, use the Session "
              "pooler connection string from Supabase → Project Settings → Database.")
        return 1

    with conn:
        for path in MIGRATIONS:
            name = os.path.basename(path)
            sql = open(path).read()
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                conn.commit()
                print(f"✓ applied {name}")
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                print(f"✗ {name} failed: {type(e).__name__}: {e}")
                return 1

        # Sanity: list created tables + seed counts.
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute("SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public' ORDER BY table_name")
            tables = [r["table_name"] for r in cur.fetchall()]
            cur.execute("SELECT count(*) AS n FROM portals")
            portals = cur.fetchone()["n"]
            cur.execute("SELECT count(*) AS n FROM settings")
            settings = cur.fetchone()["n"]
    conn.close()
    print(f"\npublic tables: {', '.join(tables)}")
    print(f"seeded: {portals} portals, {settings} settings")
    print("✅ migrations applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
