from pathlib import Path

from PIL import Image


def test_process_photo_resizes_and_outputs_jpg(tmp_path):
    from app.services.photo_processor import MAX_HEIGHT, MAX_WIDTH, process_photo

    src = tmp_path / "source.png"
    Image.new("RGB", (1800, 2400), color="red").save(src)

    out = process_photo(src, "25.3251_норма_ifsh", 1)

    assert out.suffix.lower() == ".jpg"
    assert out.exists()

    with Image.open(out) as image:
        assert image.width <= MAX_WIDTH
        assert image.height <= MAX_HEIGHT
        assert image.format == "JPEG"


def test_photo_pipeline_runs_with_mocked_dependencies(tmp_path, monkeypatch):
    from app.tasks.photo_pipeline import run_photo_pipeline

    async def mock_download(file_id: str, suffix: str = "") -> Path:
        path = tmp_path / f"{file_id}{suffix or '.jpg'}"
        Image.new("RGB", (1200, 1600), color="blue").save(path)
        return path

    sent_batches = []
    sent_messages = []

    async def mock_send_text(chat_id, text, reply_markup=None, parse_mode=None):
        sent_messages.append(text)

    async def mock_broadcast(photo_paths, code):
        sent_batches.append((list(photo_paths), code))

    monkeypatch.setattr("app.tasks.photo_pipeline.download_telegram_file", mock_download)
    monkeypatch.setattr("app.tasks.photo_pipeline.send_text", mock_send_text)
    monkeypatch.setattr("app.tasks.photo_pipeline.broadcast_photos_to_group_with_ids", mock_broadcast)

    result = run_photo_pipeline.apply(
        kwargs={
            "chat_id": "123456789",
            "file_ids": ["photo1", "photo2"],
            "code": "25.3251_норма_ifsh",
        }
    ).get()

    assert result["status"] == "done"
    assert result["count"] == 2
    assert len(sent_batches) == 1
    assert sent_batches[0][1] == "25.3251_норма_ifsh"
    assert any("[1/3]" in message for message in sent_messages)
