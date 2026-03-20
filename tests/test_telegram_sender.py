import asyncio
from unittest.mock import AsyncMock, MagicMock


class _BotStub:
    def __init__(self):
        self.calls = []
        self.session = MagicMock()
        self.session.close = AsyncMock()

    async def delete_message(self, chat_id: int, message_id: int):
        self.calls.append((chat_id, message_id))
        if message_id == 2:
            raise RuntimeError("already gone")


def test_delete_messages_continues_after_single_failure(monkeypatch):
    from app.services import telegram_sender

    bot = _BotStub()
    monkeypatch.setattr(telegram_sender, "_is_mock_token", lambda: False)
    monkeypatch.setattr(telegram_sender, "_make_bot", lambda: bot)

    result = asyncio.run(telegram_sender.delete_messages("-100555", [1, 2, 3]))

    assert result == {"deleted": 2, "failed": 1}
    assert bot.calls == [(-100555, 1), (-100555, 2), (-100555, 3)]
    bot.session.close.assert_awaited_once()
