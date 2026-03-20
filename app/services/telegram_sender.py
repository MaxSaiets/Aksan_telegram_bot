"""
Send messages and files to Telegram users/groups via aiogram Bot API.
"""
from __future__ import annotations

from pathlib import Path

from aiogram.types import BufferedInputFile, InputMediaDocument

from config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

_MOCK_TOKEN_PREFIX = "MOCK"


def _is_mock_token() -> bool:
    parts = settings.TELEGRAM_BOT_TOKEN.split(":")
    return len(parts) < 2 or _MOCK_TOKEN_PREFIX in parts[1].upper()


def _make_bot():
    from aiogram import Bot

    return Bot(token=settings.TELEGRAM_BOT_TOKEN)


async def send_text(
    chat_id: str | int,
    text: str,
    reply_markup=None,
    parse_mode: str | None = None,
) -> None:
    if _is_mock_token():
        logger.info("[MOCK Telegram] send_text -> %s | %s", str(chat_id)[:15], text[:80])
        return

    bot = _make_bot()
    try:
        await bot.send_message(
            chat_id=int(chat_id),
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    finally:
        await bot.session.close()


async def send_video_file(chat_id: str | int, video_path: Path, caption: str = "") -> int | None:
    if _is_mock_token():
        logger.info(
            "[MOCK Telegram] send_video_file -> %s | file=%s | caption=%s",
            str(chat_id)[:15], video_path.name, caption[:40],
        )
        return 1

    bot = _make_bot()
    try:
        data = video_path.read_bytes()
        message = await bot.send_video(
            chat_id=int(chat_id),
            video=BufferedInputFile(data, filename=video_path.name),
            caption=caption,
        )
        return message.message_id
    finally:
        await bot.session.close()


async def send_document(
    chat_id: str | int,
    file_path: Path,
    filename: str,
    caption: str = "",
) -> None:
    if _is_mock_token():
        logger.info("[MOCK Telegram] send_document -> %s | file=%s", str(chat_id)[:15], filename)
        return

    bot = _make_bot()
    try:
        data = file_path.read_bytes()
        await bot.send_document(
            chat_id=int(chat_id),
            document=BufferedInputFile(data, filename=filename),
            caption=caption,
        )
    finally:
        await bot.session.close()


async def broadcast_to_group(video_path: Path, caption: str) -> int | None:
    target = settings.TELEGRAM_TARGET_CHAT_ID
    if _is_mock_token():
        logger.info(
            "[MOCK Telegram] broadcast_to_group -> chat=%s | file=%s | caption=%s",
            str(target)[:15], video_path.name, caption[:60],
        )
        return 1

    return await send_video_file(target, video_path, caption)


async def broadcast_photos_to_group_with_ids(photo_paths: list[Path], code: str) -> list[int]:
    target = settings.TELEGRAM_TARGET_CHAT_ID
    if _is_mock_token():
        logger.info(
            "[MOCK Telegram] broadcast_photos_to_group_with_ids -> chat=%s | count=%d | code=%s",
            str(target)[:15], len(photo_paths), code,
        )
        return list(range(1, len(photo_paths) + 2))

    bot = _make_bot()
    sent_message_ids: list[int] = []
    try:
        chunk_size = 10
        for start in range(0, len(photo_paths), chunk_size):
            chunk = photo_paths[start:start + chunk_size]
            media = [
                InputMediaDocument(
                    media=BufferedInputFile(photo_path.read_bytes(), filename=photo_path.name),
                )
                for photo_path in chunk
            ]
            messages = await bot.send_media_group(chat_id=int(target), media=media)
            sent_message_ids.extend(message.message_id for message in messages)

        caption_message = await bot.send_message(chat_id=int(target), text=code)
        sent_message_ids.append(caption_message.message_id)
        return sent_message_ids
    finally:
        await bot.session.close()


async def delete_messages(chat_id: str | int, message_ids: list[int]) -> dict[str, int]:
    if _is_mock_token():
        logger.info("[MOCK Telegram] delete_messages -> chat=%s | ids=%s", str(chat_id)[:15], message_ids)
        return {"deleted": len(message_ids), "failed": 0}

    bot = _make_bot()
    deleted = 0
    failed = 0
    try:
        for message_id in message_ids:
            try:
                await bot.delete_message(chat_id=int(chat_id), message_id=message_id)
                deleted += 1
            except Exception as exc:
                failed += 1
                logger.warning(
                    "Failed to delete Telegram message chat=%s message_id=%s: %s",
                    str(chat_id)[:15],
                    message_id,
                    exc,
                )
        return {"deleted": deleted, "failed": failed}
    finally:
        await bot.session.close()
