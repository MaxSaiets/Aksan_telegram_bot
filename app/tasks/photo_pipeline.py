"""Celery task for multi-photo processing, archiving, and group delivery."""
from __future__ import annotations

import asyncio
from pathlib import Path

from config import settings
from app.database.photo_library_repo import photo_library_repo
from app.services.photo_batch_store import save_last_batch
from app.services.photo_processor import process_photo
from app.services.telegram_sender import broadcast_photos_to_group_with_ids, send_text
from app.tasks.celery_app import celery_app
from app.telegram.keyboard import main_menu_keyboard
from app.utils.file_manager import cleanup, download_telegram_file
from app.utils.logger import get_logger

logger = get_logger(__name__)


_STEP_1 = "[1/4] \u0417\u0430\u0432\u0430\u043d\u0442\u0430\u0436\u0443\u044e {count} \u0444\u043e\u0442\u043e \u0437 Telegram..."
_STEP_2 = "[2/4] \u0421\u0442\u0438\u0441\u043a\u0430\u044e \u0444\u043e\u0442\u043e \u0442\u0430 \u0433\u043e\u0442\u0443\u044e JPG 600x900..."
_STEP_3 = "[3/4] \u041d\u0430\u0434\u0441\u0438\u043b\u0430\u044e \u0433\u043e\u0442\u043e\u0432\u0456 JPG \u0443 \u0433\u0440\u0443\u043f\u0443..."
_STEP_4 = "[4/4] \u0417\u0431\u0435\u0440\u0456\u0433\u0430\u044e \u0444\u043e\u0442\u043e\u0430\u0440\u0445\u0456\u0432 \u0434\u043b\u044f \u043c\u043e\u0434\u0435\u043b\u0456..."
_READY = (
    "\u2705 \u0413\u043e\u0442\u043e\u0432\u043e! \u041e\u0431\u0440\u043e\u0431\u043b\u0435\u043d\u043e {count} \u0444\u043e\u0442\u043e \u0434\u043b\u044f \u043a\u043e\u0434\u0443 {code}.\n"
    "\u0410\u0440\u0445\u0456\u0432: \u043c\u043e\u0434\u0435\u043b\u044c {model}, batch {batch_id}."
)
_ERROR = "\u274c \u041d\u0435 \u0432\u0434\u0430\u043b\u043e\u0441\u044f \u043e\u0431\u0440\u043e\u0431\u0438\u0442\u0438 \u0444\u043e\u0442\u043e: {error}"


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
    """Download, optimize, archive and send a batch of photos to the target group."""
    originals: list[Path] = []
    processed: list[Path] = []

    try:
        _notify(chat_id, _STEP_1.format(count=len(file_ids)))
        for file_id in file_ids:
            original = _async(download_telegram_file(file_id, ".jpg"))
            logger.info(
                "Downloaded photo %s to %s (%d bytes)",
                file_id,
                original,
                original.stat().st_size if original.exists() else -1,
            )
            originals.append(original)

        _notify(chat_id, _STEP_2)
        for index, source_path in enumerate(originals, start=1):
            processed.append(process_photo(source_path, code, index))

        _notify(chat_id, _STEP_3)
        message_ids = _async(broadcast_photos_to_group_with_ids(processed, code))
        save_last_batch(chat_id, settings.TELEGRAM_TARGET_CHAT_ID, message_ids, code)

        photo_message_ids = message_ids[: len(processed)]
        caption_message_id = message_ids[len(processed)] if len(message_ids) > len(processed) else None

        _notify(chat_id, _STEP_4)
        batch = photo_library_repo.save_batch(
            source_chat_id=chat_id,
            target_chat_id=settings.TELEGRAM_TARGET_CHAT_ID,
            code=code,
            source_file_ids=file_ids,
            processed_paths=processed,
            target_message_ids=photo_message_ids,
            caption_message_id=caption_message_id,
        )

        _notify(
            chat_id,
            _READY.format(
                count=len(processed),
                code=code,
                model=batch.get("model_code") or "\u043d\u0435\u0432\u0456\u0434\u043e\u043c\u043e",
                batch_id=batch["id"][:8],
            ),
            reply_markup=main_menu_keyboard(),
        )
        return {"status": "done", "count": len(processed), "batch_id": batch["id"]}
    except Exception as exc:
        logger.exception("Photo pipeline failed: %s", exc)
        _notify(
            chat_id,
            _ERROR.format(error=exc),
            reply_markup=main_menu_keyboard(),
        )
        raise self.retry(exc=exc)
    finally:
        cleanup(*originals, *processed)
