"""Append-only photo library metadata stored via db_client, with JPG files archived locally."""
from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.database.client import db_client
from app.services.photo_processor import sanitize_code
from app.services.sku_parser import extract_category, extract_model_code
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PhotoLibraryRepo:
    """Store processed photo batches for later lookup and API access."""

    def __init__(self, db_path: Path | str | None = None, library_root: Path | str = Path("tmp/photo_library")):
        self.db_path = Path(db_path) if db_path is not None else None
        self.library_root = Path(library_root)

    def init(self) -> None:
        self.library_root.mkdir(parents=True, exist_ok=True)

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
        self.init()

        created_at = self._now()
        batch_id = str(uuid.uuid4())
        model_code = extract_model_code(code)
        category = extract_category(code)
        archive_dir = self._archive_dir_for_batch(model_code, code, created_at, batch_id)

        batch = db_client.insert(
            "photo_batches",
            {
                "id": batch_id,
                "source_chat_id": source_chat_id,
                "target_chat_id": target_chat_id,
                "code": code,
                "model_code": model_code,
                "category": category,
                "caption_message_id": caption_message_id,
                "photo_count": len(processed_paths),
                "created_at": created_at,
            },
        )

        items: list[dict[str, Any]] = []
        for index, processed_path in enumerate(processed_paths, start=1):
            archive_name = f"{index:02d}_{sanitize_code(code)}.jpg"
            archive_path = archive_dir / archive_name
            shutil.copy2(processed_path, archive_path)

            item = db_client.insert(
                "photo_items",
                {
                    "id": str(uuid.uuid4()),
                    "batch_id": batch_id,
                    "photo_index": index,
                    "source_file_id": source_file_ids[index - 1] if index - 1 < len(source_file_ids) else None,
                    "target_message_id": target_message_ids[index - 1] if index - 1 < len(target_message_ids) else None,
                    "archive_path": str(archive_path),
                    "filename": archive_name,
                    "created_at": created_at,
                },
            )
            items.append(item)

        logger.info(
            "Saved photo batch %s for model=%s code=%s count=%d",
            batch_id,
            model_code,
            code,
            len(items),
        )
        return {
            **batch,
            "archive_dir": str(archive_dir),
            "items": items,
        }

    def list_models(self) -> list[dict[str, Any]]:
        rows = self.list_batches(limit=5000)
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = row.get("model_code") or "unknown_model"
            bucket = grouped.setdefault(
                key,
                {
                    "model_code": key,
                    "batch_count": 0,
                    "photo_count": 0,
                    "latest_batch_at": None,
                },
            )
            bucket["batch_count"] += 1
            bucket["photo_count"] += int(row.get("photo_count") or 0)
            created_at = row.get("created_at")
            if created_at and (bucket["latest_batch_at"] is None or created_at > bucket["latest_batch_at"]):
                bucket["latest_batch_at"] = created_at
        return sorted(grouped.values(), key=lambda item: item.get("latest_batch_at") or "", reverse=True)

    def list_batches(
        self,
        *,
        model_code: str | None = None,
        code: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        rows = db_client.select("photo_batches")
        filtered = []
        for row in rows:
            if model_code and row.get("model_code") != model_code:
                continue
            if code and row.get("code") != code:
                continue
            filtered.append(row)
        filtered.sort(key=lambda row: row.get("created_at") or "", reverse=True)
        return filtered[:limit]

    def list_photos(
        self,
        *,
        model_code: str | None = None,
        code: str | None = None,
        batch_id: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        batches = self.list_batches(model_code=model_code, code=code, limit=5000)
        if batch_id:
            batches = [batch for batch in batches if batch.get("id") == batch_id]
        if not batches:
            return []

        batch_by_id = {batch["id"]: batch for batch in batches}
        items = []
        for item in db_client.select("photo_items"):
            parent = batch_by_id.get(item.get("batch_id"))
            if not parent:
                continue
            items.append(
                {
                    **item,
                    "code": parent.get("code"),
                    "model_code": parent.get("model_code"),
                    "category": parent.get("category"),
                    "source_chat_id": parent.get("source_chat_id"),
                    "target_chat_id": parent.get("target_chat_id"),
                    "caption_message_id": parent.get("caption_message_id"),
                }
            )
        items.sort(key=lambda row: ((row.get("created_at") or ""), -(row.get("photo_index") or 0)), reverse=True)
        return items[:limit]

    def get_photo(self, photo_id: str) -> dict[str, Any] | None:
        rows = db_client.select("photo_items", {"id": photo_id})
        if not rows:
            return None
        item = rows[0]
        batch = self.get_batch(item["batch_id"])
        if not batch:
            return None
        return {
            **item,
            "code": batch.get("code"),
            "model_code": batch.get("model_code"),
            "category": batch.get("category"),
            "source_chat_id": batch.get("source_chat_id"),
            "target_chat_id": batch.get("target_chat_id"),
            "caption_message_id": batch.get("caption_message_id"),
        }

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        rows = db_client.select("photo_batches", {"id": batch_id})
        return rows[0] if rows else None


photo_library_repo = PhotoLibraryRepo()

