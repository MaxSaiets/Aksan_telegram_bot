"""
Register the Telegram webhook URL with the Bot API.
Run once after deploying or changing the domain.

Usage:
    python scripts/register_webhook.py

Requires TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_URL to be set in .env
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from aiogram import Bot
from aiogram.types import BotCommand
from config import settings


async def register():
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    try:
        webhook_url = f"{settings.TELEGRAM_WEBHOOK_URL.rstrip('/')}/webhook"
        print(f"Registering webhook: {webhook_url}")

        await bot.set_webhook(
            url=webhook_url,
            secret_token=settings.TELEGRAM_WEBHOOK_SECRET,
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
        )

        # Set bot commands (shown in Telegram UI)
        await bot.set_my_commands([
            BotCommand(command="start", description="Почати роботу / головне меню"),
            BotCommand(command="help",  description="Довідка по боту"),
        ])

        info = await bot.get_webhook_info()
        print(f"OK Webhook registered: {info.url}")
        print(f"   Pending updates: {info.pending_update_count}")
        print(f"   Max connections: {info.max_connections}")
        if info.last_error_message:
            print(f"   Last error: {info.last_error_message}")

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(register())
