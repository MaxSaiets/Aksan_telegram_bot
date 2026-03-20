"""
Celery tasks: generate Rozetka / site video files and send to user via Telegram.
"""
import asyncio

from app.services.telegram_sender import send_document, send_text
from app.tasks.celery_app import celery_app
from app.telegram.keyboard import main_menu_keyboard
from app.utils.logger import get_logger
from config import settings

logger = get_logger(__name__)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=1)
def run_generate_rozetka_file(self, chat_id: str):
    logger.info("Files/Rozetka START | chat=%s", chat_id[:12])
    try:
        def _progress(msg: str) -> None:
            try:
                _run(send_text(chat_id, msg))
            except Exception:
                pass

        from app.services.files_generator import generate_rozetka_file

        path, count = generate_rozetka_file(on_progress=_progress)

        if count == 0:
            _run(send_text(
                chat_id,
                "✅ Збігів для Rozetka не знайдено.\n"
                "Відео з YouTube і товари з Rozetka були прочитані, але exact model/category не дали жодного допустимого SKU за поточними size rules.",
                reply_markup=main_menu_keyboard(),
            ))
            return {"status": "empty"}

        caption = f"🛒 Файл для Rozetka готовий: {count} рядків"

        if settings.USE_MOCKS:
            _run(send_text(
                chat_id,
                f"[MOCK] {caption}\n📄 {path.name}",
                reply_markup=main_menu_keyboard(),
            ))
        else:
            _run(send_document(
                chat_id,
                file_path=path,
                filename=path.name,
                caption=caption,
            ))
            _run(send_text(chat_id, caption, reply_markup=main_menu_keyboard()))

        logger.info("Files/Rozetka DONE | rows=%d | file=%s", count, path.name)
        return {"status": "done", "count": count, "file": str(path)}

    except Exception as exc:
        logger.exception("Files/Rozetka FAILED: %s", exc)
        _run(send_text(
            chat_id,
            f"❌ Помилка генерації файлу для Rozetka:\n{exc}",
            reply_markup=main_menu_keyboard(),
        ))
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=1)
def run_generate_site_file(self, chat_id: str):
    logger.info("Files/Site START | chat=%s", chat_id[:12])
    try:
        def _progress(msg: str) -> None:
            try:
                _run(send_text(chat_id, msg))
            except Exception:
                pass

        from app.services.files_generator import generate_site_file

        path, count = generate_site_file(on_progress=_progress)

        if count == 0:
            _run(send_text(
                chat_id,
                "✅ Збігів для сайту не знайдено.\n"
                "Відео з YouTube і товари з Rozetka були прочитані, але exact model/category не дали жодного допустимого SKU за поточними size rules.",
                reply_markup=main_menu_keyboard(),
            ))
            return {"status": "empty"}

        caption = f"🌐 Файл для сайту готовий: {count} рядків"

        if settings.USE_MOCKS:
            _run(send_text(
                chat_id,
                f"[MOCK] {caption}\n📄 {path.name}",
                reply_markup=main_menu_keyboard(),
            ))
        else:
            _run(send_document(
                chat_id,
                file_path=path,
                filename=path.name,
                caption=caption,
            ))
            _run(send_text(chat_id, caption, reply_markup=main_menu_keyboard()))

        logger.info("Files/Site DONE | rows=%d | file=%s", count, path.name)
        return {"status": "done", "count": count, "file": str(path)}

    except Exception as exc:
        logger.exception("Files/Site FAILED: %s", exc)
        _run(send_text(
            chat_id,
            f"❌ Помилка генерації файлу для сайту:\n{exc}",
            reply_markup=main_menu_keyboard(),
        ))
        raise self.retry(exc=exc)