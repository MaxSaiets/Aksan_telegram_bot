"""
Tests for the Telegram webhook endpoint and router logic.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from main import app

    with TestClient(app) as c:
        yield c


class TestWebhookEndpoint:
    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["mocks"] is True

    def test_webhook_returns_200(self, client):
        with patch("main.dp.feed_update", new_callable=AsyncMock):
            resp = client.post("/webhook", json=_tg_message(text="/start"))
        assert resp.status_code == 200

    def test_webhook_returns_400_on_invalid_json(self, client):
        resp = client.post(
            "/webhook",
            content="not-json-at-all",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    def test_webhook_accepts_callback_query(self, client):
        with patch("main.dp.feed_update", new_callable=AsyncMock):
            resp = client.post("/webhook", json=_tg_callback(data="btn_cancel"))
        assert resp.status_code == 200


class TestRouterHandlers:
    def test_cmd_start_sends_greeting(self):
        from app.telegram.router import cmd_start

        msg = _make_mock_message()
        state = _make_mock_state()
        with patch("app.telegram.router._is_allowed", return_value=True):
            asyncio.run(cmd_start(msg, state))

        msg.answer.assert_awaited_once()
        assert "TestUser" in msg.answer.call_args.args[0]

    def test_btn_send_video_sets_state(self):
        from app.telegram.router import btn_send_video
        from app.telegram.states import VideoUpload

        msg = _make_mock_message()
        state = _make_mock_state()
        with patch("app.telegram.router._is_allowed", return_value=True):
            asyncio.run(btn_send_video(msg, state))

        state.set_state.assert_awaited_once_with(VideoUpload.waiting_video)
        state.update_data.assert_awaited_once_with(queue_count=0)

    def test_btn_send_photos_sets_state(self):
        from app.telegram.router import btn_send_photos
        from app.telegram.states import PhotoUpload

        msg = _make_mock_message()
        state = _make_mock_state()
        with patch("app.telegram.router._is_allowed", return_value=True):
            asyncio.run(btn_send_photos(msg, state))

        state.set_state.assert_awaited_once_with(PhotoUpload.waiting_photos)
        state.update_data.assert_awaited_once_with(photo_file_ids=[], photo_count=0)

    def test_handle_video_dispatches_immediately(self):
        from app.telegram.router import handle_video

        msg = _make_mock_message(video={"file_id": "tg_file_id_abc123"}, caption="20.8934_РЅРѕСЂРјР°")
        state = _make_mock_state(data={"queue_count": 0})
        mock_task = MagicMock()
        mock_task.id = "fake-task-id-abcdef"

        with patch("app.tasks.video_pipeline.run_video_pipeline") as mock_pipeline:
            mock_pipeline.delay = MagicMock(return_value=mock_task)
            asyncio.run(handle_video(msg, state))

        mock_pipeline.delay.assert_called_once_with(
            chat_id="123456789",
            file_id="tg_file_id_abc123",
            caption="20.8934_РЅРѕСЂРјР°",
            message_id=1,
        )
        state.update_data.assert_awaited_once_with(queue_count=1)

    def test_handle_photo_collects_file_ids(self):
        from app.telegram.router import handle_photo

        msg = _make_mock_message(photo=[{"file_id": "small"}, {"file_id": "big"}])
        state = _make_mock_state(data={"photo_file_ids": ["one"], "photo_count": 1})

        asyncio.run(handle_photo(msg, state))

        state.update_data.assert_awaited_once_with(photo_file_ids=["one", "big"], photo_count=2)

    def test_handle_photo_document_collects_file_id(self):
        from app.telegram.router import handle_photo_document

        msg = _make_mock_message()
        msg.document = MagicMock()
        msg.document.file_id = "doc_img"
        msg.document.mime_type = "image/jpeg"
        msg.document.file_name = "img.jpg"
        state = _make_mock_state(data={"photo_file_ids": [], "photo_count": 0})

        asyncio.run(handle_photo_document(msg, state))

        state.update_data.assert_awaited_once_with(photo_file_ids=["doc_img"], photo_count=1)

    def test_handle_photo_code_dispatches_task(self):
        from app.telegram.router import handle_photo_code

        msg = _make_mock_message(text="25.3251_РЅРѕСЂРјР°_ifsh")
        state = _make_mock_state(data={"photo_file_ids": ["a", "b"]})
        mock_task = MagicMock()
        mock_task.id = "photo-task-id"

        with patch("app.tasks.photo_pipeline.run_photo_pipeline") as mock_pipeline:
            mock_pipeline.delay = MagicMock(return_value=mock_task)
            asyncio.run(handle_photo_code(msg, state))

        mock_pipeline.delay.assert_called_once_with(
            chat_id="123456789",
            file_ids=["a", "b"],
            code="25.3251_РЅРѕСЂРјР°_ifsh",
        )
        state.clear.assert_awaited_once()

    def test_delete_last_photos_button(self):
        from app.telegram.router import btn_delete_last_photos

        msg = _make_mock_message(text="рџ—‘ Р’РёРґР°Р»РёС‚Рё РїРѕРїРµСЂРµРґРЅС” С„РѕС‚Рѕ")
        with patch("app.telegram.router._is_allowed", return_value=True), \
             patch("app.telegram.router.get_last_batch", return_value={"target_chat_id": "-1001", "message_ids": [10, 11], "code": "26.2888"}), \
             patch("app.telegram.router.delete_messages", new_callable=AsyncMock) as mock_delete, \
             patch("app.telegram.router.clear_last_batch") as mock_clear:
            asyncio.run(btn_delete_last_photos(msg))

        mock_delete.assert_awaited_once_with("-1001", [10, 11])
        mock_clear.assert_called_once_with("123456789")
        msg.answer.assert_awaited_once()


class TestKeyboards:
    def test_main_menu_has_all_buttons(self):
        from aiogram.types import ReplyKeyboardMarkup
        from app.telegram.keyboard import (
            BTN_CANCEL_PHOTOS,
            BTN_DELETE_LAST_PHOTOS,
            BTN_FILES,
            BTN_RESET,
            BTN_SEND_PHOTOS,
            BTN_SEND_VIDEO,
            main_menu_keyboard,
            photo_mode_keyboard,
        )

        kb = main_menu_keyboard()
        assert isinstance(kb, ReplyKeyboardMarkup)
        texts = [btn.text for row in kb.keyboard for btn in row]
        assert BTN_SEND_VIDEO in texts
        assert BTN_SEND_PHOTOS in texts
        assert BTN_DELETE_LAST_PHOTOS in texts
        assert BTN_FILES in texts
        assert BTN_RESET in texts

        photo_kb = photo_mode_keyboard()
        photo_texts = [btn.text for row in photo_kb.keyboard for btn in row]
        assert BTN_CANCEL_PHOTOS in photo_texts


class TestFSMStates:
    def test_states_exist_and_are_distinct(self):
        from app.telegram.states import PhotoUpload, VideoUpload

        assert VideoUpload.waiting_video is not None
        assert VideoUpload.waiting_confirm is not None
        assert PhotoUpload.waiting_photos is not None
        assert VideoUpload.waiting_video != PhotoUpload.waiting_photos


class TestTelegramSender:
    def _mock_bot(self):
        bot = MagicMock()
        bot.send_message = AsyncMock()
        bot.send_video = AsyncMock()
        bot.send_document = AsyncMock()
        bot.send_media_group = AsyncMock(return_value=[MagicMock(message_id=1), MagicMock(message_id=2)])
        bot.delete_message = AsyncMock()
        bot.session = MagicMock()
        bot.session.close = AsyncMock()
        return bot

    def test_send_text_mock(self):
        from app.services import telegram_sender
        from app.services.telegram_sender import send_text

        with patch.object(telegram_sender, "_make_bot", return_value=self._mock_bot()):
            asyncio.run(send_text("123456789", "Test message"))

    def test_broadcast_photos_to_group_mock(self, tmp_path):
        from app.services import telegram_sender
        from app.services.telegram_sender import broadcast_photos_to_group_with_ids

        files = []
        for index in range(2):
            file_path = tmp_path / f"photo_{index}.jpg"
            file_path.write_bytes(b"jpg")
            files.append(file_path)

        with patch.object(telegram_sender, "_make_bot", return_value=self._mock_bot()):
            result = asyncio.run(broadcast_photos_to_group_with_ids(files, "25.3251_РЅРѕСЂРјР°_ifsh"))

        assert result == [1, 2]


def _tg_message(
    user_id: int = 123456789,
    chat_id: int | None = None,
    text: str | None = None,
    video: dict | None = None,
    caption: str | None = None,
    message_id: int = 1,
) -> dict:
    msg: dict = {
        "message_id": message_id,
        "from": {"id": user_id, "is_bot": False, "first_name": "TestUser"},
        "chat": {"id": chat_id or user_id, "type": "private", "first_name": "TestUser"},
        "date": 1700000000,
    }
    if text is not None:
        msg["text"] = text
    if video is not None:
        msg["video"] = video
    if caption is not None:
        msg["caption"] = caption
    return {"update_id": 1, "message": msg}


def _tg_callback(user_id: int = 123456789, data: str = "btn_confirm", message_id: int = 10) -> dict:
    return {
        "update_id": 2,
        "callback_query": {
            "id": "cq_123",
            "from": {"id": user_id, "is_bot": False, "first_name": "TestUser"},
            "message": {
                "message_id": message_id,
                "chat": {"id": user_id, "type": "private"},
                "date": 1700000000,
                "text": "РџС–РґС‚РІРµСЂРґРёС‚Рё?",
            },
            "chat_instance": "ci_123",
            "data": data,
        },
    }


def _make_mock_message(
    user_id=123456789,
    chat_id=None,
    text=None,
    video=None,
    photo=None,
    caption=None,
):
    msg = MagicMock()
    msg.from_user = MagicMock()
    msg.from_user.id = user_id
    msg.from_user.first_name = "TestUser"
    msg.chat = MagicMock()
    msg.chat.id = chat_id or user_id
    msg.message_id = 1
    msg.text = text
    msg.caption = caption
    msg.answer = AsyncMock()
    msg.document = None

    if video:
        msg.video = MagicMock()
        msg.video.file_id = video.get("file_id", "mock_file_id_xyz")
    else:
        msg.video = None

    if photo:
        msg.photo = []
        for item in photo:
            photo_obj = MagicMock()
            photo_obj.file_id = item["file_id"]
            msg.photo.append(photo_obj)
    else:
        msg.photo = None

    return msg


def _make_mock_state(state_name=None, data=None):
    ctx = MagicMock()
    ctx.clear = AsyncMock()
    ctx.set_state = AsyncMock()
    ctx.update_data = AsyncMock()
    ctx.get_state = AsyncMock(return_value=state_name)
    ctx.get_data = AsyncMock(return_value=data or {})
    return ctx

