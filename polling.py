"""
Run the Telegram bot in polling mode.

Useful for local Windows runs where webhook + ngrok is unstable.
"""
import asyncio

from main import bot, dp
from config import settings
from app.database.client import db_client
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def main() -> None:
    logger.info("Starting Telegram bot in polling mode (USE_MOCKS=%s)", settings.USE_MOCKS)
    db_client.init()
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        try:
            asyncio.run(bot.session.close())
        except Exception:
            pass
