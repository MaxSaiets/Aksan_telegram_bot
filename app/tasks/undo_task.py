"""Celery task: delete the last processed video."""
from __future__ import annotations

import asyncio

from app.database.videos_repo import delete_video, get_video
from app.services.telegram_sender import delete_messages, send_text
from app.services.youtube_uploader import delete_from_youtube
from app.tasks.celery_app import celery_app
from app.telegram.keyboard import main_menu_keyboard
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=1)
def run_undo_last_video(self, chat_id: str, video_id: str):
    """Delete a video from YouTube, Telegram target group, and local DB."""
    logger.info("Undo START | chat=%s video_id=%s", chat_id[:12], video_id)

    try:
        video = get_video(video_id)
        if not video:
            _run(send_text(
                chat_id,
                "⚠️ Відео не знайдено в базі.",
                reply_markup=main_menu_keyboard(),
            ))
            return {"status": "not_found"}

        youtube_url = video.get("youtube_url", "")
        caption = video.get("caption", "")
        target_chat_id = video.get("target_chat_id")
        target_message_id = video.get("target_message_id")
        results: list[str] = []

        if youtube_url and "not-configured" not in youtube_url:
            yt_ok = delete_from_youtube(youtube_url)
            if yt_ok:
                results.append("YouTube: видалено")
            else:
                results.append(
                    "YouTube: не вдалося видалити (перевірте token.json і перевидайте його через scripts/youtube_auth.py)"
                )
        else:
            results.append("YouTube: відео не було завантажено")

        if target_chat_id and target_message_id:
            delete_result = _run(delete_messages(target_chat_id, [int(target_message_id)]))
            if delete_result.get("deleted", 0) > 0 and delete_result.get("failed", 0) == 0:
                results.append("Група: відео видалено")
            elif delete_result.get("deleted", 0) > 0:
                results.append("Група: видалено частково")
            else:
                results.append("Група: не вдалося видалити")
        else:
            results.append("Група: немає збереженого message_id")

        delete_video(video_id)
        results.append("База даних: видалено")

        preview = caption[:60] + ("..." if len(caption) > 60 else "")
        details = "\n".join(f"  • {item}" for item in results)
        _run(send_text(
            chat_id,
            f"🗑 Відео видалено!\n📝 «{preview}»\n\n{details}",
            reply_markup=main_menu_keyboard(),
        ))

        logger.info("Undo DONE | video_id=%s", video_id)
        return {"status": "done", "video_id": video_id}

    except Exception as exc:
        logger.exception("Undo FAILED: %s", exc)
        _run(send_text(
            chat_id,
            f"❌ Не вдалося видалити відео: {exc}",
            reply_markup=main_menu_keyboard(),
        ))
        raise self.retry(exc=exc)
