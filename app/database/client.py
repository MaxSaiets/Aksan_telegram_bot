"""
Database client abstraction.
- USE_MOCKS=true  -> SQLite (no credentials needed, file: tmp/mock.db)
- USE_MOCKS=false -> Supabase (requires SUPABASE_URL + SUPABASE_SERVICE_KEY)
"""
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

_MOCK_DB_PATH = Path("tmp/mock.db")


class _MockDBClient:
    """In-process SQLite that mirrors the Supabase schema."""

    def __init__(self):
        self._conn: sqlite3.Connection | None = None

    def init(self):
        _MOCK_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(_MOCK_DB_PATH), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()
        logger.info("[MOCK DB] SQLite ready at %s", _MOCK_DB_PATH)

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS videos (
                id                TEXT PRIMARY KEY,
                chat_id           TEXT NOT NULL,
                caption           TEXT,
                original_url      TEXT,
                youtube_url       TEXT,
                target_chat_id    TEXT,
                target_message_id INTEGER,
                status            TEXT DEFAULT 'pending',
                error_message     TEXT,
                created_at        TEXT,
                updated_at        TEXT
            );

            CREATE TABLE IF NOT EXISTS products (
                id                      TEXT PRIMARY KEY,
                video_id                TEXT,
                model_name              TEXT,
                product_name            TEXT,
                sku                     TEXT,
                salesdrive_product_id   TEXT,
                rozetka_product_id      TEXT,
                rozetka_url             TEXT,
                youtube_url             TEXT,
                match_confidence        REAL,
                created_at              TEXT,
                updated_at              TEXT
            );

            CREATE TABLE IF NOT EXISTS photo_batches (
                id                  TEXT PRIMARY KEY,
                source_chat_id      TEXT NOT NULL,
                target_chat_id      TEXT NOT NULL,
                code                TEXT NOT NULL,
                model_code          TEXT,
                category            TEXT,
                caption_message_id  INTEGER,
                photo_count         INTEGER NOT NULL,
                created_at          TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS photo_items (
                id                  TEXT PRIMARY KEY,
                batch_id            TEXT NOT NULL,
                photo_index         INTEGER NOT NULL,
                source_file_id      TEXT,
                target_message_id   INTEGER,
                archive_path        TEXT NOT NULL,
                filename            TEXT NOT NULL,
                created_at          TEXT NOT NULL
            );
        """)
        self._ensure_column("videos", "target_chat_id", "TEXT")
        self._ensure_column("videos", "target_message_id", "INTEGER")
        self._conn.commit()

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        existing = {
            row["name"]
            for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in existing:
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ensure_init(self):
        if self._conn is None:
            self.init()

    def insert(self, table: str, data: dict) -> dict:
        self._ensure_init()
        data = {**data}
        if "id" not in data:
            data["id"] = str(uuid.uuid4())
        if "created_at" not in data:
            data["created_at"] = self._now()
        if table == "videos":
            data.setdefault("updated_at", self._now())

        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        self._conn.execute(
            f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({placeholders})",
            list(data.values()),
        )
        self._conn.commit()
        logger.debug("[MOCK DB] INSERT %s id=%s", table, data.get("id"))
        return data

    def select(self, table: str, filters: dict | None = None) -> list[dict]:
        self._ensure_init()
        query = f"SELECT * FROM {table}"
        params: list[Any] = []
        if filters:
            clauses = " AND ".join(f"{k} = ?" for k in filters)
            query += f" WHERE {clauses}"
            params = list(filters.values())
        rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def update(self, table: str, filters: dict, data: dict) -> dict | None:
        self._ensure_init()
        data = {**data, "updated_at": self._now()}
        set_clause = ", ".join(f"{k} = ?" for k in data)
        where_clause = " AND ".join(f"{k} = ?" for k in filters)
        self._conn.execute(
            f"UPDATE {table} SET {set_clause} WHERE {where_clause}",
            list(data.values()) + list(filters.values()),
        )
        self._conn.commit()
        rows = self.select(table, filters)
        return rows[0] if rows else None

    def delete(self, table: str, filters: dict) -> None:
        self._ensure_init()
        where_clause = " AND ".join(f"{k} = ?" for k in filters)
        self._conn.execute(
            f"DELETE FROM {table} WHERE {where_clause}",
            list(filters.values()),
        )
        self._conn.commit()


class _SupabaseClient:
    def __init__(self):
        self._client = None

    def init(self):
        from supabase import create_client
        self._client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
        logger.info("Supabase client ready (url=%s)", settings.SUPABASE_URL)

    def insert(self, table: str, data: dict) -> dict:
        result = self._client.table(table).insert(data).execute()
        return result.data[0]

    def select(self, table: str, filters: dict | None = None) -> list[dict]:
        q = self._client.table(table).select("*")
        if filters:
            for k, v in filters.items():
                q = q.eq(k, v)
        return q.execute().data

    def update(self, table: str, filters: dict, data: dict) -> dict | None:
        q = self._client.table(table).update(data)
        for k, v in filters.items():
            q = q.eq(k, v)
        result = q.execute()
        return result.data[0] if result.data else None

    def delete(self, table: str, filters: dict) -> None:
        q = self._client.table(table).delete()
        for k, v in filters.items():
            q = q.eq(k, v)
        q.execute()


db_client: _MockDBClient | _SupabaseClient = (
    _MockDBClient() if settings.USE_MOCKS else _SupabaseClient()
)
