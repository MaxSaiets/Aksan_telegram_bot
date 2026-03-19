"""
Telegram Video Bot — FastAPI + aiogram v3

Architecture:
  - FastAPI handles the HTTP layer (webhook endpoint + health check)
  - aiogram Bot + Dispatcher processes Telegram updates with built-in FSM
  - Celery workers handle heavy tasks (download, FFmpeg, YouTube upload)
  - Redis stores FSM state (real mode) or MemoryStorage (mock mode)
"""
import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update

from config import settings
from app.utils.logger import get_logger
from app.telegram.router import router as telegram_router
from app.database.client import db_client

logger = get_logger(__name__)


# ── Bot & Dispatcher ──────────────────────────────────────────────────────────

def _make_storage():
    """Use MemoryStorage in mock mode (no Redis needed), RedisStorage in production."""
    if settings.USE_MOCKS:
        return MemoryStorage()
    from aiogram.fsm.storage.redis import RedisStorage
    return RedisStorage.from_url(settings.REDIS_URL)


bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
dp = Dispatcher(storage=_make_storage())
dp.include_router(telegram_router)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Telegram Video Bot (USE_MOCKS=%s)", settings.USE_MOCKS)
    db_client.init()

    if not settings.USE_MOCKS:
        webhook_url = f"{settings.TELEGRAM_WEBHOOK_URL.rstrip('/')}/webhook"
        await bot.set_webhook(
            url=webhook_url,
            secret_token=settings.TELEGRAM_WEBHOOK_SECRET,
            allowed_updates=["message", "callback_query"],
        )
        info = await bot.get_webhook_info()
        logger.info("Webhook registered: %s (pending=%d)", info.url, info.pending_update_count)
    else:
        logger.info("Mock mode — webhook not registered (use polling or send mock requests)")

    yield

    if not settings.USE_MOCKS:
        await bot.delete_webhook(drop_pending_updates=False)
    await bot.session.close()
    logger.info("Shutting down Telegram Video Bot")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Telegram Video Bot",
    version="2.0.0",
    lifespan=lifespan,
)


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@app.post("/webhook")
async def telegram_webhook(request: Request) -> Response:
    """
    Receive Telegram updates.
    In real mode, verify the X-Telegram-Bot-Api-Secret-Token header.
    Always returns 200 so Telegram doesn't retry on processing errors.
    """
    # Signature verification (skipped in mock mode)
    if not settings.USE_MOCKS:
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if secret != settings.TELEGRAM_WEBHOOK_SECRET:
            logger.warning("Invalid Telegram webhook secret — rejected")
            return Response(status_code=403)

    try:
        data = await request.json()
    except Exception:
        return Response(status_code=400)

    update = Update.model_validate(data)
    await dp.feed_update(bot=bot, update=update)
    return Response(status_code=200)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "mocks": settings.USE_MOCKS})


# ── Dev entrypoint ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level=settings.LOG_LEVEL.lower(),
    )
