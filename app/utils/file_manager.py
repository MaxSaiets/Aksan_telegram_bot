"""Utilities for downloading, managing, and cleaning up temporary video files."""
import io
import shutil
import uuid
from pathlib import Path

from config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


def get_temp_path(suffix: str = ".mp4") -> Path:
    """Generate a unique temporary file path inside the configured temp directory."""
    settings.temp_dir  # ensures the directory exists
    return settings.temp_dir / f"{uuid.uuid4().hex}{suffix}"


async def download_telegram_file(file_id: str, suffix: str = "") -> Path:
    """Download any Telegram file via Bot API."""
    dest = get_temp_path(suffix)
    return await _download_via_bot_api(file_id, dest)


async def _download_via_bot_api(file_id: str, dest: Path) -> Path:
    """Download using standard Bot API getFile (limit 20 MB)."""
    from aiogram import Bot
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    try:
        tg_file = await bot.get_file(file_id)
        buffer = io.BytesIO()
        await bot.download_file(tg_file.file_path, destination=buffer)
        dest.write_bytes(buffer.getvalue())
        logger.info("Downloaded file via Bot API to %s (%d bytes)", dest, dest.stat().st_size)
    finally:
        await bot.session.close()
    return dest


async def _download_via_mtproto(chat_id: int, message_id: int, dest: Path) -> Path:
    """
    Download using telethon MTProto (no size limit).
    Requires TELEGRAM_API_ID and TELEGRAM_API_HASH in .env.
    """
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    client = TelegramClient(
        StringSession(),
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH,
    )
    await client.start(bot_token=settings.TELEGRAM_BOT_TOKEN)
    try:
        message = await client.get_messages(chat_id, ids=message_id)
        if not message or not message.media:
            raise ValueError("Message or media not found via MTProto")
        await client.download_media(message, file=str(dest))
        return dest
    finally:
        await client.disconnect()


async def download_telegram_media(
    file_id: str,
    chat_id: int | None = None,
    message_id: int | None = None,
) -> Path:
    """
    Download a Telegram video file to local temp storage.

    Tries Bot API first (fast, but 20 MB limit).
    Falls back to MTProto via telethon for larger files.
    """
    dest = get_temp_path(".mp4")

    try:
        return await _download_via_bot_api(file_id, dest)
    except Exception as exc:
        err = str(exc).lower()
        if "file is too big" not in err and "file_is_too_big" not in err:
            raise  # not a size issue, re-raise

        logger.warning("File too big for Bot API (>20 MB), trying MTProto...")

        # Check MTProto credentials
        if not settings.TELEGRAM_API_ID or not settings.TELEGRAM_API_HASH:
            raise RuntimeError(
                "Файл завеликий для Bot API (>20 МБ).\n\n"
                "Для підтримки великих файлів додайте в .env:\n"
                "TELEGRAM_API_ID=ваш_id\n"
                "TELEGRAM_API_HASH=ваш_hash\n\n"
                "Отримати: https://my.telegram.org → API development tools"
            ) from exc

        if chat_id is None or message_id is None:
            raise RuntimeError(
                "Файл завеликий для Bot API (>20 МБ), "
                "а MTProto не може знайти повідомлення (відсутній chat_id/message_id)."
            ) from exc

        result = await _download_via_mtproto(chat_id, message_id, dest)
        logger.info(
            "Downloaded via MTProto to %s (%.1f MB)",
            dest, dest.stat().st_size / (1024 * 1024),
        )
        return result


def copy_file(src: Path, suffix: str = "_processed.mp4") -> Path:
    """Copy a file to a new temp path (used for mock processing)."""
    dest = get_temp_path(suffix)
    shutil.copy2(src, dest)
    return dest


def cleanup(*paths: Path) -> None:
    """Delete temporary files after processing."""
    for path in paths:
        try:
            if path and path.exists():
                path.unlink()
                logger.debug("Deleted temp file: %s", path)
        except Exception as exc:
            logger.warning("Failed to delete %s: %s", path, exc)
