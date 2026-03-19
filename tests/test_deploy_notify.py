import asyncio
from unittest.mock import AsyncMock, patch


def test_resolve_deploy_notify_chat_id_from_explicit_value(monkeypatch):
    from config import settings
    from app.services.deploy_notify import resolve_deploy_notify_chat_id

    monkeypatch.setattr(settings, "DEPLOY_NOTIFY_CHAT_ID", "1311004971")
    monkeypatch.setattr(settings, "TELEGRAM_ALLOWED_USERS", "")

    assert resolve_deploy_notify_chat_id() == "1311004971"


def test_resolve_deploy_notify_chat_id_from_allowed_users(monkeypatch):
    from config import settings
    from app.services.deploy_notify import resolve_deploy_notify_chat_id

    monkeypatch.setattr(settings, "DEPLOY_NOTIFY_CHAT_ID", "")
    monkeypatch.setattr(settings, "TELEGRAM_ALLOWED_USERS", "1311004971, 555")

    assert resolve_deploy_notify_chat_id() == "1311004971"


def test_send_deploy_notification_uses_project_sender(monkeypatch):
    from config import settings
    from app.services.deploy_notify import send_deploy_notification

    monkeypatch.setattr(settings, "DEPLOY_NOTIFY_CHAT_ID", "1311004971")
    monkeypatch.setattr(settings, "TELEGRAM_ALLOWED_USERS", "")

    with patch("app.services.deploy_notify.send_text", new_callable=AsyncMock) as mock_send:
        result = asyncio.run(send_deploy_notification("abc1234"))

    assert result is True
    mock_send.assert_awaited_once_with("1311004971", "Я оновився. Commit: abc1234")
