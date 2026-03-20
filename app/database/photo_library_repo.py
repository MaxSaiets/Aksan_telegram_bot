"""Append-only photo library backed by local SQLite and archived JPG files."""
from __future__ import annotations

import shutil
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.photo_processor import sanitize_code
from app.services.sku_parser import extract_category, extract_model_code
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PhotoLibraryRepo:
    """Store processed photo batches for later lookup and API access."""

    def __init__(
        self,
        db_path: Path | str = Path("tmp/photo_library.db"),
        library_root: Path | str = Path("tmp/photo_library"),
    ):
        self.db_path = Path(db_path)
        self.library_root = Path(library_root)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    def init(self) -> None:
        with self._lock:
            if self._conn is not None:
                return

            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.library_root.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._create_tables()
            logger.info("Photo library ready at %s", self.db_path)

    def _ensure_init(self) -> None:
        if self._conn is None:
            self.init()

    def _create_tables(self) -> None:
        self._conn.executescript(
            """
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
                created_at          TEXT NOT NULL,
                FOREIGN KEY (batch_id) REFERENCES photo_batches(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_photo_batches_model_code
            ON photo_batches(model_code);

            CREATE INDEX IF NOT EXISTS idx_photo_batches_code
            ON photo_batches(code);

            CREATE INDEX IF NOT EXISTS idx_photo_items_batch_id
            ON photo_items(batch_id);
            """
        )
        self._conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _archive_dir_for_batch(self, model_code: str | None, code: str, created_at: str, batch_id: str) -> Path:
        timestamp = created_at.replace(":", "-")
        model_dir = sanitize_code(model_code or "unknown_model")
        code_dir = sanitize_code(code)
        batch_dir = self.library_root / model_dir / f"{timestamp}_{code_dir}_{batch_id[:8]}"
        batch_dir.mkdir(parents=True, exist_ok=True)
        return batch_dir

    def save_batch(
        self,
        *,
        source_chat_id: str,
        target_chat_id: str,
        code: str,
        source_file_ids: list[str],
        processed_paths: list[Path],
        target_message_ids: list[int],
        caption_message_id: int | None = None,
    ) -> dict[str, Any]:
        """Archive processed JPGs and save append-only metadata."""
        self._ensure_init()

        created_at = self._now()
        batch_id = str(uuid.uuid4())
        model_code = extract_model_code(code)
        category = extract_category(code)
        archive_dir = self._archive_dir_for_batch(model_code, code, created_at, batch_id)

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO photo_batches (
                    id, source_chat_id, target_chat_id, code, model_code,
                    category, caption_message_id, photo_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    source_chat_id,
                    target_chat_id,
                    code,
                    model_code,
                    category,
                    caption_message_id,
                    len(processed_paths),
                    created_at,
                ),
            )

            items: list[dict[str, Any]] = []
            for index, processed_path in enumerate(processed_paths, start=1):
                item_id = str(uuid.uuid4())
                archive_name = f"{index:02d}_{sanitize_code(code)}.jpg"
                archive_path = archive_dir / archive_name
                shutil.copy2(processed_path, archive_path)

                row = {
                    "id": item_id,
                    "batch_id": batch_id,
                    "photo_index": index,
                    "source_file_id": source_file_ids[index - 1] if index - 1 < len(source_file_ids) else None,
                    "target_message_id": target_message_ids[index - 1] if index - 1 < len(target_message_ids) else None,
                    "archive_path": str(archive_path),
                    "filename": archive_name,
                    "created_at": created_at,
                }
                self._conn.execute(
                    """
                    INSERT INTO photo_items (
                        id, batch_id, photo_index, source_file_id,
                        target_message_id, archive_path, filename, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["id"],
                        row["batch_id"],
                        row["photo_index"],
                        row["source_file_id"],
                        row["target_message_id"],
                        row["archive_path"],
                        row["filename"],
                        row["created_at"],
                    ),
                )
                items.append(row)

            self._conn.commit()

        logger.info(
            "Saved photo batch %s for model=%s code=%s count=%d",
            batch_id,
            model_code,
            code,
            len(items),
        )
        return {
            "id": batch_id,
            "source_chat_id": source_chat_id,
            "target_chat_id": target_chat_id,
            "code": code,
            "model_code": model_code,
            "category": category,
            "caption_message_id": caption_message_id,
            "photo_count": len(items),
            "created_at": created_at,
            "archive_dir": str(archive_dir),
            "items": items,
        }

    def list_models(self) -> list[dict[str, Any]]:
        self._ensure_init()
        rows = self._conn.execute(
            """
            SELECT
                COALESCE(model_code, 'unknown_model') AS model_code,
                COUNT(*) AS batch_count,
                SUM(photo_count) AS photo_count,
                MAX(created_at) AS latest_batch_at
            FROM photo_batches
            GROUP BY COALESCE(model_code, 'unknown_model')
            ORDER BY latest_batch_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def list_batches(
        self,
        *,
        model_code: str | None = None,
        code: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self._ensure_init()
        clauses: list[str] = []
        params: list[Any] = []
        if model_code:
            clauses.append("model_code = ?")
            params.append(model_code)
        if code:
            clauses.append("code = ?")
            params.append(code)

        query = "SELECT * FROM photo_batches"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def list_photos(
        self,
        *,
        model_code: str | None = None,
        code: str | None = None,
        batch_id: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        self._ensure_init()
        clauses: list[str] = []
        params: list[Any] = []

        if model_code:
            clauses.append("b.model_code = ?")
            params.append(model_code)
        if code:
            clauses.append("b.code = ?")
            params.append(code)
        if batch_id:
            clauses.append("b.id = ?")
            params.append(batch_id)

        query = """
            SELECT
                i.id,
                i.batch_id,
                i.photo_index,
                i.source_file_id,
                i.target_message_id,
                i.archive_path,
                i.filename,
                i.created_at,
                b.code,
                b.model_code,
                b.category,
                b.source_chat_id,
                b.target_chat_id,
                b.caption_message_id
            FROM photo_items i
            JOIN photo_batches b ON b.id = i.batch_id
        """
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY i.created_at DESC, i.photo_index ASC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_photo(self, photo_id: str) -> dict[str, Any] | None:
        self._ensure_init()
        row = self._conn.execute(
            """
            SELECT
                i.id,
                i.batch_id,
                i.photo_index,
                i.source_file_id,
                i.target_message_id,
                i.archive_path,
                i.filename,
                i.created_at,
                b.code,
                b.model_code,
                b.category,
                b.source_chat_id,
                b.target_chat_id,
                b.caption_message_id
            FROM photo_items i
            JOIN photo_batches b ON b.id = i.batch_id
            WHERE i.id = ?
            """,
            (photo_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        self._ensure_init()
        row = self._conn.execute(
            "SELECT * FROM photo_batches WHERE id = ?",
            (batch_id,),
        ).fetchone()
        return dict(row) if row else None


photo_library_repo = PhotoLibraryRepo()
