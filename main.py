"""
Telegram Video Bot - FastAPI + aiogram v3.

Architecture:
  - FastAPI handles the HTTP layer (webhook endpoint + health check)
  - aiogram Bot + Dispatcher processes Telegram updates with built-in FSM
  - Celery workers handle heavy tasks (download, FFmpeg, YouTube upload)
  - Redis stores FSM state (real mode) or MemoryStorage (mock mode)
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update

from config import settings
from app.database.client import db_client
from app.database.photo_library_repo import photo_library_repo
from app.telegram.router import router as telegram_router
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _make_storage():
    """Use MemoryStorage in mock mode (no Redis needed), RedisStorage in production."""
    if settings.USE_MOCKS:
        return MemoryStorage()
    from aiogram.fsm.storage.redis import RedisStorage
    return RedisStorage.from_url(settings.REDIS_URL)


bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
dp = Dispatcher(storage=_make_storage())
dp.include_router(telegram_router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Telegram Video Bot (USE_MOCKS=%s)", settings.USE_MOCKS)
    db_client.init()
    photo_library_repo.init()

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
        logger.info("Mock mode - webhook not registered (use polling or send mock requests)")

    yield

    if not settings.USE_MOCKS:
        await bot.delete_webhook(drop_pending_updates=False)
    await bot.session.close()
    logger.info("Shutting down Telegram Video Bot")


app = FastAPI(
    title="Telegram Video Bot",
    version="2.0.0",
    lifespan=lifespan,
)


@app.post("/webhook")
async def telegram_webhook(request: Request) -> Response:
    """
    Receive Telegram updates.
    In real mode, verify the X-Telegram-Bot-Api-Secret-Token header.
    Always returns 200 so Telegram doesn't retry on processing errors.
    """
    if not settings.USE_MOCKS:
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if secret != settings.TELEGRAM_WEBHOOK_SECRET:
            logger.warning("Invalid Telegram webhook secret - rejected")
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


def _photo_payload(row: dict) -> dict:
    file_path = Path(row["archive_path"])
    return {
        **row,
        "file_exists": file_path.exists(),
        "file_size": file_path.stat().st_size if file_path.exists() else None,
        "download_url": f"/api/photo-library/photos/{row['id']}/download",
    }


@app.get("/api/photo-library/models")
async def api_photo_models() -> JSONResponse:
    items = photo_library_repo.list_models()
    return JSONResponse({"count": len(items), "items": items})


@app.get("/api/photo-library/batches")
async def api_photo_batches(
    model_code: str | None = Query(default=None),
    code: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> JSONResponse:
    items = photo_library_repo.list_batches(model_code=model_code, code=code, limit=limit)
    return JSONResponse({"count": len(items), "items": items})


@app.get("/api/photo-library/batches/{batch_id}")
async def api_photo_batch(batch_id: str) -> JSONResponse:
    batch = photo_library_repo.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Photo batch not found")

    photos = [
        _photo_payload(item)
        for item in photo_library_repo.list_photos(batch_id=batch_id, limit=1000)
    ]
    return JSONResponse({"batch": batch, "photos": photos})


@app.get("/api/photo-library/photos")
async def api_photo_items(
    model_code: str | None = Query(default=None),
    code: str | None = Query(default=None),
    batch_id: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
) -> JSONResponse:
    items = [
        _photo_payload(item)
        for item in photo_library_repo.list_photos(
            model_code=model_code,
            code=code,
            batch_id=batch_id,
            limit=limit,
        )
    ]
    return JSONResponse({"count": len(items), "items": items})


@app.get("/api/photo-library/photos/{photo_id}")
async def api_photo_item(photo_id: str) -> JSONResponse:
    item = photo_library_repo.get_photo(photo_id)
    if not item:
        raise HTTPException(status_code=404, detail="Photo not found")
    return JSONResponse(_photo_payload(item))


@app.get("/api/photo-library/photos/{photo_id}/download")
async def api_photo_download(photo_id: str) -> FileResponse:
    item = photo_library_repo.get_photo(photo_id)
    if not item:
        raise HTTPException(status_code=404, detail="Photo not found")

    file_path = Path(item["archive_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archived photo file not found")

    return FileResponse(path=file_path, media_type="image/jpeg", filename=item["filename"])


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level=settings.LOG_LEVEL.lower(),
    )
