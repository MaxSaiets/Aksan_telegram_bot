"""One-off copy of all Supabase tables into the local SQLite database.

Usage (from the project root):
    python scripts/migrate_supabase_to_sqlite.py [--db data/aksan.db]

Safe to re-run: rows are upserted by id. Nothing is changed in Supabase.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TABLES = ("videos", "products", "photo_batches", "photo_items")
PAGE = 1000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=None, help="SQLite file (default: LOCAL_DB_PATH)")
    args = parser.parse_args()

    from config import settings
    from app.database.client import _MockDBClient, _local_db_path

    target = Path(args.db) if args.db else _local_db_path()
    if not target.is_absolute():
        target = ROOT / target

    if not settings.SUPABASE_URL or "mock" in settings.SUPABASE_URL:
        print("SUPABASE_URL is not configured - nothing to migrate.")
        return 0

    import httpx

    base = settings.SUPABASE_URL.rstrip("/") + "/rest/v1"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
    }
    local = _MockDBClient(target)
    local.init()

    total = 0
    for table in TABLES:
        columns = {
            row["name"] for row in local._conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        copied = 0
        offset = 0
        while True:
            response = httpx.get(
                f"{base}/{table}",
                params={"select": "*", "order": "created_at.asc", "limit": PAGE, "offset": offset},
                headers=headers,
                timeout=60,
            )
            response.raise_for_status()
            rows = response.json()
            for row in rows:
                data = {k: v for k, v in row.items() if k in columns}
                cols = ", ".join(data)
                marks = ", ".join("?" for _ in data)
                local._conn.execute(
                    f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({marks})", list(data.values())
                )
                copied += 1
            local._conn.commit()
            if len(rows) < PAGE:
                break
            offset += PAGE
        print(f"{table}: {copied} rows copied")
        total += copied

    print(f"Done: {total} rows -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
