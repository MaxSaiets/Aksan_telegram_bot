"""
Celery task: undo (delete) the last processed video.

Steps:
  1. Delete from YouTube
  2. Delete from DB (videos + products)
  3. Remove from exported files (so regenerated files won't reference it)
  4. Notify user
"""
import asyncio

from app.tasks.celery_app import celery_app
from app.utils.logger import get_logger
from app.services.youtube_uploader import delete_from_youtube
from app.services.telegram_sender import send_text
from app.telegram.keyboard import main_menu_keyboard
from app.database.videos_repo import get_video, delete_video
from app.database.products_repo import get_products_for_video

logger = get_logger(__name__)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=1)
def run_undo_last_video(self, chat_id: str, video_id: str):
    """
    Delete a video completely: YouTube + DB + exported sets.
    """
    logger.info("Undo START | chat=%s video_id=%s", chat_id[:12], video_id)

    try:
        video = get_video(video_id)
        if not video:
            _run(send_text(
                chat_id,
                "⚠️ Відео не знайдено в базі даних.",
                reply_markup=main_menu_keyboard(),
            ))
            return {"status": "not_found"}

        youtube_url = video.get("youtube_url", "")
        caption = video.get("caption", "")
        results = []

        # 1. Delete from YouTube
        if youtube_url and "not-configured" not in youtube_url:
            yt_ok = delete_from_youtube(youtube_url)
            results.append(f"YouTube: {'видалено' if yt_ok else 'не вдалось видалити'}")
        else:
            results.append("YouTube: відео не було завантажено")

        # 2. Remove from exported files
        products = get_products_for_video(video_id)
        for p in products:
            sku = p.get("sku")
            model = p.get("model_name")
            if sku or model:
                try:
                    from app.services.files_generator import remove_from_exported
                    remove_from_exported(sku or "", model or "")
                except Exception:
                    pass

        # 3. Delete from DB
        delete_video(video_id)
        results.append("База даних: видалено")

        details = "\n".join(f"  • {r}" for r in results)
        preview = caption[:60] + ("..." if len(caption) > 60 else "")

        _run(send_text(
            chat_id,
            f"🗑 Відео видалено!\n"
            f"📝 «{preview}»\n\n"
            f"{details}",
            reply_markup=main_menu_keyboard(),
        ))

        logger.info("Undo DONE | video_id=%s", video_id)
        return {"status": "done", "video_id": video_id}

    except Exception as exc:
        logger.exception("Undo FAILED | video_id=%s | %s", video_id, exc)
        _run(send_text(
            chat_id,
            f"❌ Помилка видалення відео:\n{exc}",
            reply_markup=main_menu_keyboard(),
        ))
        raise self.retry(exc=exc)
