"""
Shared pytest fixtures.
All tests run with USE_MOCKS=true and an isolated SQLite DB.
"""
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# Force mocks BEFORE any project imports
os.environ["USE_MOCKS"] = "true"
os.environ["TEMP_VIDEO_DIR"] = "tmp/test_videos"

from config import settings
from app.database.client import db_client, _MockDBClient


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """
    Each test gets a fresh SQLite database so tests don't interfere.
    Also mocks download_telegram_media so tests never hit the real Telegram API.
    """
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("app.database.client._MOCK_DB_PATH", db_path)

    fresh_client = _MockDBClient()
    fresh_client.init()
    monkeypatch.setattr("app.database.client.db_client", fresh_client)

    # Patch the db_client in all repos too
    import app.database.videos_repo as vr
    import app.database.products_repo as pr
    monkeypatch.setattr(vr, "db_client", fresh_client)
    monkeypatch.setattr(pr, "db_client", fresh_client)

    # Mock Telegram download — tests use fake file_ids, never hit real API
    async def _mock_download(file_id: str, chat_id=None, message_id=None) -> Path:
        p = tmp_path / f"mock_{file_id[:16]}.mp4"
        p.write_bytes(b"\x00" * 1024)
        return p

    monkeypatch.setattr("app.utils.file_manager.download_telegram_media", _mock_download)
    monkeypatch.setattr("app.tasks.video_pipeline.download_telegram_media", _mock_download)

    # Mock FFmpeg overlay — tests don't need real video processing
    def _mock_overlay(input_path: Path, text: str) -> Path:
        import shutil as _shutil
        out = input_path.parent / (input_path.stem + "_captioned.mp4")
        _shutil.copy2(input_path, out)
        return out

    monkeypatch.setattr("app.services.video_editor.overlay_text", _mock_overlay)
    monkeypatch.setattr("app.tasks.video_pipeline.overlay_text", _mock_overlay)

    yield fresh_client


@pytest.fixture
def sample_catalog():
    """Numeric-code catalog matching the real model format (25.2834 / 5.52.2554)."""
    return [
        {"id": "1", "sku": "25.2834",   "model": "25.2834",   "name": "Дриль 800Вт"},
        {"id": "2", "sku": "5.52.2554", "model": "5.52.2554", "name": "Перфоратор 1200Вт"},
        {"id": "3", "sku": "12.4567",   "model": "12.4567",   "name": "Болгарка 125мм"},
    ]


@pytest.fixture
def sample_rozetka():
    return [
        {"id": "R1", "model": "25.2834",   "sku": "25.2834",   "url": "https://rozetka.com.ua/drill-800w"},
        {"id": "R2", "model": "5.52.2554", "sku": "5.52.2554", "url": "https://rozetka.com.ua/perforator-1200w"},
    ]


@pytest.fixture
def temp_video(tmp_path) -> Path:
    """A 1 KB dummy video file."""
    p = tmp_path / "test_video.mp4"
    p.write_bytes(b"\x00" * 1024)
    return p
