from __future__ import annotations

import asyncio
import sys

from config import settings
from app.services.telegram_sender import send_text
from app.utils.logger import get_logger

logger = get_logger(__name__)


def resolve_deploy_notify_chat_id() -> str | None:
    chat_id = (settings.DEPLOY_NOTIFY_CHAT_ID or "").strip()
    if chat_id:
        return chat_id

    allowed_users = (settings.TELEGRAM_ALLOWED_USERS or "").split(",")
    for value in allowed_users:
        value = value.strip()
        if value:
            return value
    return None


def build_deploy_message(commit_sha: str) -> str:
    commit_sha = (commit_sha or "").strip() or "unknown"
    return f"Я оновився. Commit: {commit_sha}"


async def send_deploy_notification(commit_sha: str) -> bool:
    chat_id = resolve_deploy_notify_chat_id()
    if not chat_id:
        logger.info("Deploy notification skipped: no chat id configured")
        return False

    await send_text(chat_id, build_deploy_message(commit_sha))
    logger.info("Deploy notification sent to %s", str(chat_id)[:20])
    return True


def main() -> int:
    commit_sha = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        asyncio.run(send_deploy_notification(commit_sha))
        return 0
    except Exception as exc:
        logger.warning("Deploy notification failed: %s", exc)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
