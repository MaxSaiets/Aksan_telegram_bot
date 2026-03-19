"""
Supabase Storage service.
Uploads processed video files and returns a public URL for Telegram bot.

- USE_MOCKS=true  → returns a fake public URL (no upload)
- USE_MOCKS=false → uploads to Supabase Storage bucket

Setup (do once in Supabase Dashboard):
  Storage → New bucket → Name: "processed-videos" → Public: ON
"""
import uuid
from pathlib import Path

from config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def upload_file(file_path: Path, content_type: str = "application/octet-stream") -> str:
    """
    Upload any file to Supabase Storage and return its public URL.
    - USE_MOCKS=true  → returns a fake URL
    - USE_MOCKS=false → uploads to Supabase Storage
    """
    bucket = settings.SUPABASE_STORAGE_BUCKET
    remote_name = f"{uuid.uuid4().hex}_{file_path.name}"

    if settings.USE_MOCKS:
        url = (
            f"https://mock.supabase.co/storage/v1/object/public"
            f"/{bucket}/{remote_name}"
        )
        logger.info(
            "[MOCK Storage] '%s' (%d KB) => %s",
            file_path.name,
            file_path.stat().st_size // 1024 if file_path.exists() else 0,
            url,
        )
        return url

    from app.database.client import db_client

    with open(file_path, "rb") as f:
        data = f.read()

    public_url = db_client.upload_file(bucket, remote_name, data, content_type)
    logger.info(
        "Uploaded to Supabase Storage: %s (%d KB) => %s",
        file_path.name, len(data) // 1024, public_url,
    )
    return public_url


async def upload_processed_video(video_path: Path) -> str:
    """Upload a processed video file to Supabase Storage."""
    return await upload_file(video_path, "video/mp4")
