from unittest.mock import AsyncMock, patch

from app.database.videos_repo import create_video, get_video, set_done


def test_video_pipeline_persists_group_metadata_fields(tmp_path):
    from app.tasks.video_pipeline import run_video_pipeline

    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")

    async def fake_download(file_id: str, chat_id=None, message_id=None):
        return source

    with patch("app.tasks.video_pipeline.download_telegram_media", side_effect=fake_download), \
         patch("app.tasks.video_pipeline.overlay_text", side_effect=lambda path, _: path), \
         patch("app.tasks.video_pipeline.upload_to_youtube", return_value="https://youtube.com/watch?v=meta"), \
         patch("app.tasks.video_pipeline.broadcast_to_group", new=AsyncMock(return_value=777)):
        result = run_video_pipeline.apply(
            kwargs={"chat_id": "123456789", "file_id": "file_meta_1", "caption": "25.2888_норма_aksan"},
        ).get()

    assert result["status"] == "done"
    video = get_video(result["video_id"])
    assert "target_chat_id" in video
    assert "target_message_id" in video


def test_undo_last_video_deletes_group_message_and_db_record():
    from app.tasks.undo_task import run_undo_last_video

    video = create_video("123456789", "25.2888_норма_aksan", "telegram-file-id")
    set_done(video["id"], "https://youtube.com/watch?v=delete-me", "-100123", 456)

    with patch("app.tasks.undo_task.delete_from_youtube", return_value=True) as delete_youtube, \
         patch("app.tasks.undo_task.delete_messages", return_value={"deleted": 1, "failed": 0}) as delete_group:
        result = run_undo_last_video.apply(
            kwargs={"chat_id": "123456789", "video_id": video["id"]},
        ).get()

    assert result["status"] == "done"
    assert get_video(video["id"]) is None
    delete_youtube.assert_called_once_with("https://youtube.com/watch?v=delete-me")
    delete_group.assert_called_once_with("-100123", [456])
