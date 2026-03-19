"""
Integration tests: full pipeline synchronously (bypasses Celery broker).
All external calls mocked via USE_MOCKS=true.
"""
import pytest
from unittest.mock import patch
from pathlib import Path

from app.database.videos_repo import get_video, get_all_done, find_duplicate
from app.database.products_repo import get_all_products


def _run(chat_id: str, file_id: str, caption: str) -> dict:
    """Execute the pipeline synchronously using task.apply()."""
    from app.tasks.video_pipeline import run_video_pipeline
    result = run_video_pipeline.apply(
        kwargs={"chat_id": chat_id, "file_id": file_id, "caption": caption}
    )
    return result.get()


class TestVideoPipeline:

    def test_creates_video_record(self):
        r = _run("123456789", "file_id_v1_abc", "25.2834 дриль")
        assert r["status"] == "done"
        video = get_video(r["video_id"])
        assert video is not None
        assert video["status"] == "done"

    def test_saves_youtube_url(self):
        r = _run("123456789", "file_id_v2_abc", "5.52.2554 перфоратор")
        video = get_video(r["video_id"])
        assert video["youtube_url"] is not None
        assert "youtube.com" in video["youtube_url"]

    def test_matches_numeric_code(self):
        _run("123456789", "file_id_v4_abc", "25.2834 дриль")
        products = get_all_products()
        matched = [p for p in products if p["sku"] == "25.2834"]
        assert len(matched) == 1
        assert matched[0]["match_confidence"] == 1.0

    def test_saves_product_name(self):
        _run("123456789", "file_id_vpn_abc", "25.2834 дриль")
        products = get_all_products()
        matched = [p for p in products if p["sku"] == "25.2834"]
        assert len(matched) == 1
        assert matched[0].get("product_name") == "Дриль електричний 800Вт"

    def test_unmatched_model_still_saves_video(self):
        r = _run("123456789", "file_id_v5_abc", "99.9999 невідомий товар")
        assert r["status"] == "done"
        products = get_all_products()
        unmatched = [p for p in products if p["sku"] is None]
        assert len(unmatched) >= 1

    def test_multiple_runs_accumulate_records(self):
        captions = ["25.2834 дриль", "5.52.2554 перф", "12.4567 болгарка"]
        for i, cap in enumerate(captions):
            _run(f"10000000{i}", f"file_id_multi_{i}", cap)

        done_videos = get_all_done()
        assert len(done_videos) == 3

    def test_deduplication_skips_same_file_id(self):
        file_id = "file_id_duplicate_xyz"
        # First run — should process
        r1 = _run("123456789", file_id, "25.2834 дриль")
        assert r1["status"] == "done"

        # Second run with same file_id — should be detected as duplicate
        r2 = _run("123456789", file_id, "25.2834 дриль")
        assert r2["status"] == "duplicate"
        assert r2["video_id"] == r1["video_id"]

    def test_deduplication_different_file_ids_both_processed(self):
        r1 = _run("111111111", "file_id_unique_a", "25.2834")
        r2 = _run("222222222", "file_id_unique_b", "25.2834")
        assert r1["status"] == "done"
        assert r2["status"] == "done"
        assert r1["video_id"] != r2["video_id"]

    def test_find_duplicate_repo(self):
        file_id = "file_id_check_xyz"
        r = _run("123456789", file_id, "25.2834")
        dup = find_duplicate(file_id)
        assert dup is not None
        assert dup["id"] == r["video_id"]

    def test_cleans_up_temp_files(self, tmp_path, monkeypatch):
        created_files = []

        async def mock_download(file_id: str, chat_id=None, message_id=None):
            p = tmp_path / "mock_video.mp4"
            p.write_bytes(b"\x00" * 512)
            created_files.append(p)
            return p

        monkeypatch.setattr(
            "app.tasks.video_pipeline.download_telegram_media", mock_download
        )
        _run("123456789", "file_id_cleanup_abc", "25.2834 cleanup")

        for f in created_files:
            assert not f.exists(), f"Temp file not cleaned up: {f}"

    def test_status_notifications_sent(self):
        """Pipeline should send multiple progress notifications."""
        sent_messages = []

        async def capture_send(chat_id, text, reply_markup=None, parse_mode=None):
            sent_messages.append(text)

        with patch("app.tasks.video_pipeline.send_text", side_effect=capture_send):
            _run("123456789", "file_id_notify_abc", "5.52.2554")

        # Should have sent step notifications + final result
        assert len(sent_messages) >= 3
        # At least one message should contain step progress [N/M]
        progress_msgs = [m for m in sent_messages if "[" in m and "/" in m]
        assert len(progress_msgs) >= 1
