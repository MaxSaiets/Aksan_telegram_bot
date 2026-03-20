"""CRUD operations for the `videos` table."""
import uuid
from datetime import datetime, timezone

from app.database.client import db_client
from app.utils.logger import get_logger

logger = get_logger(__name__)


def create_video(chat_id: str, caption: str, original_url: str) -> dict:
    """
    Create a new video record with status='pending'.
    `original_url` stores the Telegram file_id used as a deduplication key.
    """
    data = {
        "id": str(uuid.uuid4()),
        "chat_id": chat_id,
        "caption": caption,
        "original_url": original_url,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    row = db_client.insert("videos", data)
    logger.info("Created video record id=%s chat=%s", row["id"], chat_id)
    return row


def get_video(video_id: str) -> dict | None:
    rows = db_client.select("videos", {"id": video_id})
    return rows[0] if rows else None


def set_processing(video_id: str) -> dict | None:
    return db_client.update("videos", {"id": video_id}, {"status": "processing"})


def set_done(
    video_id: str,
    youtube_url: str,
    target_chat_id: str | None = None,
    target_message_id: int | None = None,
) -> dict | None:
    payload = {"status": "done", "youtube_url": youtube_url}
    if target_chat_id is not None:
        payload["target_chat_id"] = str(target_chat_id)
    if isinstance(target_message_id, int):
        payload["target_message_id"] = target_message_id
    return db_client.update("videos", {"id": video_id}, payload)


def set_error(video_id: str, error_message: str) -> dict | None:
    return db_client.update(
        "videos",
        {"id": video_id},
        {"status": "error", "error_message": error_message},
    )


def get_all_done() -> list[dict]:
    """Return all videos with status='done'."""
    return db_client.select("videos", {"status": "done"})


def get_recent_by_chat(chat_id: str, limit: int = 5) -> list[dict]:
    """Return the N most recent completed videos for a chat."""
    rows = db_client.select("videos", {"chat_id": chat_id, "status": "done"})
    return sorted(rows, key=lambda r: r.get("created_at", ""), reverse=True)[:limit]


def get_last_done_by_chat(chat_id: str) -> dict | None:
    """Return the most recent completed video for a chat."""
    rows = db_client.select("videos", {"chat_id": chat_id, "status": "done"})
    if not rows:
        return None
    return sorted(rows, key=lambda r: r.get("created_at", ""), reverse=True)[0]


def delete_video(video_id: str) -> None:
    """Hard-delete a video record and its related products."""
    db_client.delete("products", {"video_id": video_id})
    db_client.delete("videos", {"id": video_id})
    logger.info("Deleted video id=%s and related products", video_id)


def find_duplicate(original_url: str) -> dict | None:
    """
    Check if this exact Telegram file_id was already successfully processed.
    Returns the existing video record, or None if not found.
    Used for deduplication - avoids re-uploading the same video twice.
    """
    rows = db_client.select("videos", {"original_url": original_url, "status": "done"})
    return rows[0] if rows else None
