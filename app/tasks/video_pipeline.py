"""
Main Celery task: orchestrates the full video processing pipeline.

Steps:
  0. Deduplication check — skip if same file_id was already processed
  1. Create pending DB record
  2. Download the video from Telegram servers via Bot API
  3. Upload the original to YouTube       [status: "Завантажую на YouTube..."]
  4. Overlay caption text with FFmpeg     [status: "Монтую відео..."]
  5. Send processed video to target group [status: "Надсилаю в групу..."]
  6. Fetch SalesDrive + Rozetka catalogs  [status: "Шукаю модель..."]
  7. Fuzzy-match the model code + save SKU to DB
  8. Notify user with results + main_menu
  9. Cleanup temp files

Retry: up to 2 retries; user gets "Спроба N/M не вдалась..." on each failure.
"""
import asyncio
from pathlib import Path

from celery.contrib.abortable import AbortableTask

from app.tasks.celery_app import celery_app
from app.utils.logger import get_logger
from app.utils.file_manager import download_telegram_media, cleanup
from app.services.youtube_uploader import upload_to_youtube
from app.services.video_editor import overlay_text
from app.services.telegram_sender import send_text, broadcast_to_group
from app.services.salesdrive import fetch_catalog as sd_catalog
from app.services.rozetka import fetch_catalog as rz_catalog
from app.services.model_matcher import match_model
from app.database.videos_repo import (
    create_video, set_processing, set_done, set_error, find_duplicate,
)
from app.database.products_repo import upsert_product
from app.telegram.keyboard import main_menu_keyboard

logger = get_logger(__name__)

_MAX_RETRIES = 2


def _mark_for_reexport(sku: str, model_code: str) -> None:
    """
    When a model gets a new video, remove it from exported sets
    so it will appear in the next file generation.
    """
    try:
        from app.services.files_generator import remove_from_exported
        remove_from_exported(sku, model_code)
        logger.info("Marked for re-export: sku=%s model=%s", sku, model_code)
    except Exception as exc:
        logger.warning("Could not mark for re-export: %s", exc)


def _diagnose_error(exc: Exception) -> str | None:
    """
    Analyze an exception and return a user-friendly explanation
    if it's a known key/token/config issue. Returns None for unknown errors.
    """
    err = str(exc).lower()

    # YouTube OAuth token expired / revoked
    if any(kw in err for kw in ["token has been expired", "token has been revoked", "invalid_grant"]):
        return (
            "🔑 YouTube токен прострочений або відкликаний.\n\n"
            "Як виправити:\n"
            "1. Видаліть файл token.json\n"
            "2. Запустіть: python scripts/youtube_auth.py\n"
            "3. Авторизуйтесь у браузері\n"
            "4. Перезапустіть бота"
        )

    # YouTube quota exceeded
    if "quotaexceeded" in err or "quota" in err:
        return (
            "📊 Вичерпано добову квоту YouTube API.\n\n"
            "YouTube дає 10,000 units/день. Upload = 1,600 units.\n"
            "Квота оновлюється о 00:00 за тихоокеанським часом (10:00 Київ).\n"
            "Спробуйте завтра або збільшіть квоту в Google Cloud Console."
        )

    # YouTube credentials file missing
    if "token.json" in err and "not found" in err:
        return (
            "🔑 Файл token.json не знайдено.\n\n"
            "Як виправити:\n"
            "1. Запустіть: python scripts/youtube_auth.py\n"
            "2. Авторизуйтесь у браузері\n"
            "3. Перезапустіть бота"
        )

    # YouTube API errors (403, invalid credentials)
    if "httpError 403" in err.lower() or "forbidden" in err:
        return (
            "🚫 YouTube API відмовив у доступі (403 Forbidden).\n\n"
            "Можливі причини:\n"
            "• YouTube Data API не увімкнено в Google Cloud Console\n"
            "• OAuth-додаток ще не пройшов верифікацію\n"
            "• Токен не має потрібних прав (scopes)\n\n"
            "Перегенеруйте токен: python scripts/youtube_auth.py"
        )

    # Supabase key errors
    if "apikey" in err or ("supabase" in err and ("invalid" in err or "401" in err or "403" in err)):
        return (
            "🔑 Помилка ключа Supabase.\n\n"
            "Перевірте .env:\n"
            "• SUPABASE_URL — правильна адреса проекту\n"
            "• SUPABASE_SERVICE_KEY — service_role ключ (не anon!)\n\n"
            "Знайти ключі: Supabase Dashboard → Settings → API"
        )

    # Supabase JWT expired
    if "jwt" in err and "expired" in err:
        return (
            "🔑 Supabase JWT токен прострочений.\n\n"
            "Оновіть SUPABASE_SERVICE_KEY у файлі .env.\n"
            "Знайти новий ключ: Supabase Dashboard → Settings → API → service_role"
        )

    # Redis connection
    if "redis" in err and ("connection" in err or "refused" in err):
        return (
            "🔌 Не вдалось підключитись до Redis.\n\n"
            "Перевірте:\n"
            "• Redis запущений: docker compose ps\n"
            "• REDIS_URL у .env вказує на правильну адресу\n"
            "• Порт 6379 не зайнятий іншим процесом"
        )

    # Telegram bot token invalid
    if "unauthorized" in err and "bot" in err:
        return (
            "🔑 Невірний Telegram Bot Token.\n\n"
            "Перевірте TELEGRAM_BOT_TOKEN у .env.\n"
            "Отримати новий: @BotFather → /mybots → API Token"
        )

    # Rozetka API
    if "rozetka" in err and ("401" in err or "403" in err or "unauthorized" in err):
        return (
            "🔑 Помилка ключа Rozetka API.\n\n"
            "Перевірте ROZETKA_API_KEY у .env.\n"
            "Отримати: Rozetka Seller → Налаштування → API"
        )

    # Telegram file too big (20 MB limit for Bot API getFile)
    if "file is too big" in err or "file_is_too_big" in err:
        return (
            "📦 Файл завеликий для Telegram Bot API (ліміт 20 МБ).\n\n"
            "Як вирішити:\n"
            "• Надсилайте відео як «відео» (не як файл/документ) — "
            "Telegram автоматично стисне його\n"
            "• Обріжте або стисніть відео перед відправкою\n"
            "• Використовуйте коротше відео (до 1-2 хвилин)\n\n"
            "⚙️ Технічно: Telegram Bot API обмежує завантаження "
            "файлів методом getFile до 20 МБ."
        )

    # Network / timeout
    if "timeout" in err or "connecttimeout" in err:
        return (
            "⏱ Таймаут з'єднання.\n\n"
            "Зовнішній сервіс не відповів вчасно.\n"
            "Спробуйте ще раз через кілька хвилин."
        )

    # Not a known config issue
    return None


def _async(coro):
    """Run an async coroutine from a synchronous Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _notify(chat_id: str, text: str, reply_markup=None) -> None:
    """Fire-and-forget user notification (swallows errors so pipeline continues)."""
    try:
        _async(send_text(chat_id, text, reply_markup=reply_markup))
    except Exception as exc:
        logger.warning("Could not notify chat %s: %s", chat_id[:12], exc)


def _status(chat_id: str, step: int, total: int, message: str) -> None:
    """Send a step progress notification."""
    _notify(chat_id, f"[{step}/{total}] {message}")


# ─────────────────────────────────────────────────────────────────────────────

@celery_app.task(bind=True, base=AbortableTask, max_retries=_MAX_RETRIES, default_retry_delay=20)
def run_video_pipeline(self, chat_id: str, file_id: str, caption: str, message_id: int | None = None):
    """
    Full pipeline Celery task.

    Args:
        chat_id:  Telegram chat ID (string) — used for progress notifications.
        file_id:  Telegram file_id of the uploaded video.
        caption:  Text caption — expected to contain a numeric model code
                  (e.g. "25.2834" or "5.52.2554") plus optional description.
    """
    logger.info(
        "Pipeline START | chat=%s | caption='%s'",
        chat_id[:12], caption[:60],
    )

    _TOTAL_STEPS = 6

    # ── Step 0: Deduplication ─────────────────────────────────────────────────
    existing = find_duplicate(file_id)
    if existing:
        logger.info(
            "Duplicate detected: file_id already processed as video_id=%s",
            existing["id"],
        )
        _notify(
            chat_id,
            f"⚠️ Це відео вже оброблялось раніше.\n"
            f"YouTube: {existing.get('youtube_url', '—')}\n"
            f"Пропускаємо повторну обробку.",
            reply_markup=main_menu_keyboard(),
        )
        return {"status": "duplicate", "video_id": existing["id"]}

    # ── Step 1: Create pending DB record ──────────────────────────────────────
    video_record = create_video(chat_id, caption, file_id)
    video_id = video_record["id"]

    local_path:     Path | None = None
    processed_path: Path | None = None

    try:
        set_processing(video_id)

        def _cancelled() -> bool:
            """Check if user pressed the cancel button."""
            if self.is_aborted():
                set_error(video_id, "Скасовано користувачем")
                _notify(chat_id, "❌ Обробку відео скасовано.", reply_markup=main_menu_keyboard())
                logger.info("Pipeline CANCELLED by user | video_id=%s", video_id)
                return True
            return False

        # ── Step 1: Download video from Telegram ─────────────────────────────
        _status(chat_id, 1, _TOTAL_STEPS, "Завантажую відео з Telegram...")
        local_path = _async(download_telegram_media(
            file_id,
            chat_id=int(chat_id),
            message_id=message_id,
        ))

        if _cancelled():
            return {"status": "cancelled", "video_id": video_id}

        # ── Step 2: Upload original to YouTube ────────────────────────────────
        _status(chat_id, 2, _TOTAL_STEPS, "Завантажую на YouTube...")
        youtube_url = upload_to_youtube(
            local_path,
            title=caption or "Відео без підпису",
            description=f"Завантажено через Telegram bot | Chat: {chat_id}",
        )
        logger.info("YouTube URL: %s", youtube_url)

        if _cancelled():
            return {"status": "cancelled", "video_id": video_id}

        # ── Step 3: FFmpeg text overlay ───────────────────────────────────────
        _status(chat_id, 3, _TOTAL_STEPS, "Монтую відео (накладаю підпис)...")
        processed_path = overlay_text(local_path, caption)

        if _cancelled():
            return {"status": "cancelled", "video_id": video_id}

        # ── Step 4: Send processed video to target Telegram group ─────────────
        _status(chat_id, 4, _TOTAL_STEPS, "Надсилаю в цільову групу...")
        _async(broadcast_to_group(processed_path, caption))

        if _cancelled():
            return {"status": "cancelled", "video_id": video_id}

        # ── Step 5: Match model in catalogs ───────────────────────────────────
        _status(chat_id, 5, _TOTAL_STEPS, "Шукаю модель у каталозі...")
        salesdrive = sd_catalog()
        rozetka    = rz_catalog()
        result     = match_model(caption, salesdrive, rozetka)
        logger.info(
            "Match: sku=%s strategy=%s confidence=%.0f%%",
            result.sku, result.match_strategy, result.confidence * 100,
        )

        # ── Step 6: Save to DB + notify ───────────────────────────────────────
        _status(chat_id, 6, _TOTAL_STEPS, "Зберігаю результати...")
        set_done(video_id, youtube_url)
        product, is_update = upsert_product(
            video_id=video_id,
            model_name=result.model_name,
            product_name=result.product_name,
            sku=result.sku,
            youtube_url=youtube_url,
            salesdrive_product_id=result.salesdrive_id,
            rozetka_product_id=result.rozetka_id,
            rozetka_url=result.rozetka_url,
            match_confidence=result.confidence,
        )

        if result.matched:
            update_tag = " (оновлено)" if is_update else ""
            match_info = (
                f"🏷 Артикул: {result.sku}{update_tag}\n"
                f"📊 Впевненість: {result.confidence * 100:.0f}%\n"
                f"🔎 Стратегія: {result.match_strategy}\n"
                + (f"🛒 Rozetka: {result.rozetka_url}" if result.rozetka_url else "")
            )
            if is_update:
                # Mark this SKU for re-export in files
                _mark_for_reexport(result.sku, result.model_name)
        else:
            match_info = "⚠️ Модель не знайдена у каталозі."

        _notify(
            chat_id,
            f"✅ Готово!\n"
            f"▶️ YouTube: {youtube_url}\n"
            f"─────────────────\n"
            f"{match_info}",
            reply_markup=main_menu_keyboard(),
        )

        logger.info("Pipeline DONE | video_id=%s", video_id)
        return {
            "status": "done",
            "video_id": video_id,
            "youtube_url": youtube_url,
        }

    except Exception as exc:
        set_error(video_id, str(exc))
        logger.exception("Pipeline FAILED | video_id=%s | %s", video_id, exc)

        # ── Diagnose common key/token errors and send clear explanation ──
        error_msg = _diagnose_error(exc)

        attempt     = self.request.retries + 1
        max_attempt = _MAX_RETRIES + 1

        if error_msg:
            # Key/token issue — no point in retrying, notify with explanation
            _notify(
                chat_id,
                f"❌ Помилка конфігурації:\n\n{error_msg}",
                reply_markup=main_menu_keyboard(),
            )
            # Don't retry for configuration errors
            return {"status": "config_error", "video_id": video_id, "error": str(exc)}

        if attempt < max_attempt:
            _notify(
                chat_id,
                f"⚠️ Спроба {attempt}/{max_attempt} не вдалась: {exc}\n"
                f"Автоматично повторюю через 20 сек...",
            )
        else:
            _notify(
                chat_id,
                f"❌ Всі {max_attempt} спроби вичерпано.\n"
                f"Остання помилка: {exc}\n"
                f"Спробуйте надіслати відео ще раз.",
                reply_markup=main_menu_keyboard(),
            )

        raise self.retry(exc=exc)

    finally:
        cleanup(local_path, processed_path)
