"""
Celery task: generate an Excel report and deliver it to the requesting user.

- USE_MOCKS=true  → sends a text notification with the filename
- USE_MOCKS=false → sends the .xlsx file directly via Telegram send_document
"""
import asyncio

from app.tasks.celery_app import celery_app
from app.utils.logger import get_logger
from app.services.excel_exporter import generate_report
from app.services.telegram_sender import send_text, send_document
from app.telegram.keyboard import main_menu_keyboard
from config import settings

logger = get_logger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=1)
def run_export(self, chat_id: str):
    """
    Generate .xlsx report and deliver it to the user.

    Mock mode:  sends a text notification with the filename.
    Real mode:  sends the file directly via Telegram as a document.
    """
    logger.info("Export START | chat=%s", chat_id[:12])

    try:
        def _progress(msg: str) -> None:
            try:
                _run_async(send_text(chat_id, msg))
            except Exception:
                pass

        report_path = generate_report(on_progress=_progress)
        file_size = report_path.stat().st_size if report_path.exists() else 0

        if settings.USE_MOCKS:
            _run_async(send_text(
                chat_id,
                f"📊 Звіт сформовано!\n"
                f"📄 Файл: {report_path.name} ({file_size // 1024} KB)",
                reply_markup=main_menu_keyboard(),
            ))
        else:
            _run_async(send_document(
                chat_id,
                file_path=report_path,
                filename=report_path.name,
                caption="📊 Ваш звіт готовий!",
            ))
            _run_async(send_text(
                chat_id,
                "📊 Звіт надіслано!",
                reply_markup=main_menu_keyboard(),
            ))

        logger.info("Export DONE | file=%s size=%d B", report_path, file_size)
        return {"status": "done", "path": str(report_path)}

    except Exception as exc:
        logger.exception("Export FAILED: %s", exc)
        _run_async(send_text(chat_id, f"❌ Помилка генерації звіту: {exc}"))
        raise self.retry(exc=exc)
