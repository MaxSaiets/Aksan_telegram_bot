"""
Integration tests: full pipeline synchronously (bypasses Celery broker).
"""
from pathlib import Path
from unittest.mock import patch

from app.database.videos_repo import find_duplicate, get_all_done, get_video


def _run(chat_id: str, file_id: str, caption: str) -> dict:
    from app.tasks.video_pipeline import run_video_pipeline

    result = run_video_pipeline.apply(
        kwargs={"chat_id": chat_id, "file_id": file_id, "caption": caption},
    )
    return result.get()


class TestVideoPipeline:
    def test_creates_video_record(self):
        result = _run("123456789", "file_id_v1_abc", "25.2834 дриль")
        assert result["status"] == "done"
        video = get_video(result["video_id"])
        assert video is not None
        assert video["status"] == "done"

    def test_saves_youtube_url(self):
        result = _run("123456789", "file_id_v2_abc", "5.52.2554 перфоратор")
        video = get_video(result["video_id"])
        assert "youtube.com" in video["youtube_url"]

    def test_unmatched_model_still_saves_video(self):
        result = _run("123456789", "file_id_v5_abc", "99.9999 невідомий товар")
        assert result["status"] == "done"

    def test_multiple_runs_accumulate_records(self):
        captions = ["25.2834 дриль", "5.52.2554 перф", "12.4567 болгарка"]
        for index, caption in enumerate(captions):
            _run(f"10000000{index}", f"file_id_multi_{index}", caption)

        done_videos = get_all_done()
        assert len(done_videos) == 3

    def test_deduplication_skips_same_file_id(self):
        file_id = "file_id_duplicate_xyz"
        first = _run("123456789", file_id, "25.2834 дриль")
        second = _run("123456789", file_id, "25.2834 дриль")
        assert first["status"] == "done"
        assert second["status"] == "duplicate"
        assert second["video_id"] == first["video_id"]

    def test_find_duplicate_repo(self):
        file_id = "file_id_check_xyz"
        result = _run("123456789", file_id, "25.2834")
        duplicate = find_duplicate(file_id)
        assert duplicate is not None
        assert duplicate["id"] == result["video_id"]

    def test_cleans_up_temp_files(self, tmp_path, monkeypatch):
        created_files = []

        async def mock_download(file_id: str, chat_id=None, message_id=None):
            path = tmp_path / "mock_video.mp4"
            path.write_bytes(b"\x00" * 512)
            created_files.append(path)
            return path

        monkeypatch.setattr("app.tasks.video_pipeline.download_telegram_media", mock_download)
        _run("123456789", "file_id_cleanup_abc", "25.2834 cleanup")

        for file_path in created_files:
            assert not file_path.exists()

    def test_status_notifications_sent(self):
        sent_messages = []

        async def capture_send(chat_id, text, reply_markup=None, parse_mode=None):
            sent_messages.append(text)

        with patch("app.tasks.video_pipeline.send_text", side_effect=capture_send):
            _run("123456789", "file_id_notify_abc", "5.52.2554")

        assert len(sent_messages) >= 3
        assert any("[" in message and "/" in message for message in sent_messages)

    def test_pipeline_does_not_lookup_catalogs(self, tmp_path):
        source = tmp_path / "video.mp4"
        source.write_bytes(b"video")

        async def fake_download(file_id: str, chat_id=None, message_id=None):
            return source

        with patch("app.tasks.video_pipeline.download_telegram_media", side_effect=fake_download), \
             patch("app.tasks.video_pipeline.overlay_text", side_effect=lambda path, _: path), \
             patch("app.tasks.video_pipeline.upload_to_youtube", return_value="https://youtube.com/watch?v=test"), \
             patch("app.tasks.video_pipeline.broadcast_to_group"):
            result = _run("123456789", "file_id_nomatch_1", "25.2834_норма")

        assert result["status"] == "done"

    def test_pipeline_uploads_without_telegram_description(self, tmp_path):
        source = tmp_path / "video.mp4"
        source.write_bytes(b"video")
        captured = {}

        async def fake_download(file_id: str, chat_id=None, message_id=None):
            return source

        def fake_upload(video_path, title, description="", on_progress=None):
            captured["title"] = title
            captured["description"] = description
            return "https://youtube.com/watch?v=testdesc"

        with patch("app.tasks.video_pipeline.download_telegram_media", side_effect=fake_download), \
             patch("app.tasks.video_pipeline.overlay_text", side_effect=lambda path, _: path), \
             patch("app.tasks.video_pipeline.upload_to_youtube", side_effect=fake_upload), \
             patch("app.tasks.video_pipeline.broadcast_to_group"):
            result = _run("123456789", "file_id_desc_1", "25.2888_норма_aksan")

        assert result["status"] == "done"
        assert captured["title"] == "25.2888_норма_aksan"
        assert captured["description"] == ""
