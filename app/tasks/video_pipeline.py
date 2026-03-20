"""
Main Celery task: orchestrates the full video processing pipeline.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from config import settings
from celery.contrib.abortable import AbortableTask

from app.database.videos_repo import (
    create_video,
    find_duplicate,
    set_done,
    set_error,
    set_processing,
)
from app.services.telegram_sender import broadcast_to_group, send_text
from app.services.video_editor import overlay_text
from app.services.youtube_uploader import upload_to_youtube
from app.tasks.celery_app import celery_app
from app.telegram.keyboard import main_menu_keyboard
from app.utils.file_manager import cleanup, download_telegram_media
from app.utils.logger import get_logger

logger = get_logger(__name__)

_MAX_RETRIES = 2


def _diagnose_error(exc: Exception) -> str | None:
    err = str(exc).lower()

    if any(kw in err for kw in ["token has been expired", "token has been revoked", "invalid_grant"]):
        return (
            "🔑 YouTube токен прострочений або відкликаний.\n\n"
            "Що зробити:\n"
            "1. Видаліть token.json\n"
            "2. Запустіть: python scripts/youtube_auth.py\n"
            "3. Пройдіть авторизацію в браузері\n"
            "4. Перезапустіть бота"
        )

    if "quotaexceeded" in err or "quota" in err:
        return (
            "📊 Вичерпано добову квоту YouTube API.\n\n"
            "Спробуйте пізніше або збільшіть квоту в Google Cloud Console."
        )

    if "token.json" in err and "not found" in err:
        return (
            "🔑 token.json не знайдено.\n\n"
            "Запустіть: python scripts/youtube_auth.py"
        )

    if "httperror 403" in err or "forbidden" in err:
        return (
            "🚫 YouTube API відмовив у доступі (403 Forbidden).\n\n"
            "Перевірте YouTube Data API та OAuth налаштування."
        )

    if "redis" in err and ("connection" in err or "refused" in err):
        return (
            "🔌 Не вдалося підключитись до Redis.\n\n"
            "Перевірте, що Redis запущений і REDIS_URL правильний."
        )

    if "unauthorized" in err and "bot" in err:
        return (
            "🔑 Невірний Telegram bot token.\n\n"
            "Перевірте TELEGRAM_BOT_TOKEN у .env."
        )

    if "file is too big" in err or "file_is_too_big" in err:
        return (
            "📦 Файл завеликий для Telegram Bot API.\n\n"
            "Надсилайте відео коротше або як звичайне відео, а не документ."
        )

    if "timeout" in err or "connecttimeout" in err:
        return (
            "⏱ Зовнішній сервіс не відповів вчасно.\n\n"
            "Спробуйте ще раз через кілька хвилин."
        )

    return None


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


def _status(chat_id: str, step: int, total: int, message: str) -> None:
    _notify(chat_id, f"[{step}/{total}] {message}")


@celery_app.task(bind=True, base=AbortableTask, max_retries=_MAX_RETRIES, default_retry_delay=20)
def run_video_pipeline(self, chat_id: str, file_id: str, caption: str, message_id: int | None = None):
    """
    Process one incoming video.

    Important:
    - During video upload we do not search the catalog anymore.
    - SKU/category analysis is deferred to file generation based on YouTube titles.
    """
    logger.info("Pipeline START | chat=%s | caption='%s'", chat_id[:12], caption[:60])

    total_steps = 4
    existing = find_duplicate(file_id)
    if existing:
        _notify(
            chat_id,
            f"⚠️ Це відео вже оброблялось раніше.\nYouTube: {existing.get('youtube_url', '—')}",
            reply_markup=main_menu_keyboard(),
        )
        return {"status": "duplicate", "video_id": existing["id"]}

    video_record = create_video(chat_id, caption, file_id)
    video_id = video_record["id"]

    local_path: Path | None = None
    processed_path: Path | None = None

    try:
        set_processing(video_id)

        def _cancelled() -> bool:
            if self.is_aborted():
                set_error(video_id, "Скасовано користувачем")
                _notify(chat_id, "❌ Обробку відео скасовано.", reply_markup=main_menu_keyboard())
                logger.info("Pipeline CANCELLED by user | video_id=%s", video_id)
                return True
            return False

        _status(chat_id, 1, total_steps, "Завантажую відео з Telegram...")
        local_path = _async(download_telegram_media(
            file_id,
            chat_id=int(chat_id),
            message_id=message_id,
        ))

        if _cancelled():
            return {"status": "cancelled", "video_id": video_id}

        _status(chat_id, 2, total_steps, "Завантажую на YouTube...")
        youtube_url = upload_to_youtube(
            local_path,
            title=caption or "Відео без підпису",
            description="",
        )
        logger.info("YouTube URL: %s", youtube_url)

        if _cancelled():
            return {"status": "cancelled", "video_id": video_id}

        _status(chat_id, 3, total_steps, "Монтую відео...")
        processed_path = overlay_text(local_path, caption)

        if _cancelled():
            return {"status": "cancelled", "video_id": video_id}

        _status(chat_id, 4, total_steps, "Надсилаю в цільову групу...")
        group_message_id = _async(broadcast_to_group(processed_path, caption))

        set_done(video_id, youtube_url, settings.TELEGRAM_TARGET_CHAT_ID, group_message_id)
        _notify(
            chat_id,
            f"✅ Готово!\n▶️ YouTube: {youtube_url}",
            reply_markup=main_menu_keyboard(),
        )

        logger.info("Pipeline DONE | video_id=%s", video_id)
        return {"status": "done", "video_id": video_id, "youtube_url": youtube_url}

    except Exception as exc:
        set_error(video_id, str(exc))
        logger.exception("Pipeline FAILED | video_id=%s | %s", video_id, exc)

        error_msg = _diagnose_error(exc)
        attempt = self.request.retries + 1
        max_attempt = _MAX_RETRIES + 1

        if error_msg:
            _notify(
                chat_id,
                f"❌ Помилка конфігурації:\n\n{error_msg}",
                reply_markup=main_menu_keyboard(),
            )
            return {"status": "config_error", "video_id": video_id, "error": str(exc)}

        if attempt < max_attempt:
            _notify(
                chat_id,
                f"⚠️ Спроба {attempt}/{max_attempt} не вдалась: {exc}\nАвтоматично повторюю через 20 сек...",
            )
        else:
            _notify(
                chat_id,
                f"❌ Всі {max_attempt} спроби вичерпано.\nОстання помилка: {exc}",
                reply_markup=main_menu_keyboard(),
            )

        raise self.retry(exc=exc)

    finally:
        cleanup(local_path, processed_path)
