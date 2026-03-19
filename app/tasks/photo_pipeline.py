"""Celery task for multi-photo processing and group delivery."""
from __future__ import annotations

import asyncio
from pathlib import Path

from config import settings
from app.services.photo_batch_store import save_last_batch
from app.services.photo_processor import process_photo
from app.services.telegram_sender import broadcast_photos_to_group_with_ids, send_text
from app.tasks.celery_app import celery_app
from app.telegram.keyboard import main_menu_keyboard
from app.utils.file_manager import cleanup, download_telegram_file
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _notify(chat_id: str, text: str, reply_markup=None) -> None:
    try:
        _async(send_text(chat_id, text, reply_markup=reply_markup))
    except Exception as exc:
        logger.warning("Could not notify chat %s: %s", chat_id[:12], exc)


@celery_app.task(bind=True, max_retries=1, default_retry_delay=10)
def run_photo_pipeline(self, chat_id: str, file_ids: list[str], code: str):
    """Download, optimize and send a batch of photos to the target group."""
    originals: list[Path] = []
    processed: list[Path] = []

    try:
        _notify(chat_id, f"[1/3] Завантажую {len(file_ids)} фото з Telegram...")
        for file_id in file_ids:
            original = _async(download_telegram_file(file_id, ".jpg"))
            logger.info(
                "Downloaded photo %s to %s (%d bytes)",
                file_id,
                original,
                original.stat().st_size if original.exists() else -1,
            )
            originals.append(original)

        _notify(chat_id, "[2/3] Стискаю фото та готую JPG 600x900...")
        for index, source_path in enumerate(originals, start=1):
            processed.append(process_photo(source_path, code, index))

        _notify(chat_id, "[3/3] Надсилаю готові JPG у групу...")
        message_ids = _async(broadcast_photos_to_group_with_ids(processed, code))
        save_last_batch(chat_id, settings.TELEGRAM_TARGET_CHAT_ID, message_ids, code)

        _notify(
            chat_id,
            f"✅ Готово! Оброблено {len(processed)} фото для коду {code}.",
            reply_markup=main_menu_keyboard(),
        )
        return {"status": "done", "count": len(processed)}
    except Exception as exc:
        logger.exception("Photo pipeline failed: %s", exc)
        _notify(
            chat_id,
            f"❌ Не вдалося обробити фото: {exc}",
            reply_markup=main_menu_keyboard(),
        )
        raise self.retry(exc=exc)
    finally:
        cleanup(*originals, *processed)
