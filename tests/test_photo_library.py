from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image


def _make_jpg(path: Path, color: str) -> None:
    Image.new("RGB", (640, 960), color=color).save(path, format="JPEG")


def test_photo_library_repo_appends_batches(tmp_path):
    from app.database.photo_library_repo import PhotoLibraryRepo

    repo = PhotoLibraryRepo(tmp_path / "photo_library.db", tmp_path / "photo_library")

    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    third = tmp_path / "third.jpg"
    _make_jpg(first, "red")
    _make_jpg(second, "blue")
    _make_jpg(third, "green")

    batch_one = repo.save_batch(
        source_chat_id="123",
        target_chat_id="-1001",
        code="25.3251_norma_ifsh",
        source_file_ids=["file-a", "file-b"],
        processed_paths=[first, second],
        target_message_ids=[101, 102],
        caption_message_id=103,
    )
    batch_two = repo.save_batch(
        source_chat_id="123",
        target_chat_id="-1001",
        code="25.3251_norma_ifsh",
        source_file_ids=["file-c"],
        processed_paths=[third],
        target_message_ids=[201],
        caption_message_id=202,
    )

    batches = repo.list_batches(model_code="25.3251")
    photos = repo.list_photos(model_code="25.3251")
    models = repo.list_models()

    assert batch_one["id"] != batch_two["id"]
    assert len(batches) == 2
    assert len(photos) == 3
    assert models[0]["model_code"] == "25.3251"
    assert models[0]["photo_count"] == 3
    assert all(Path(item["archive_path"]).exists() for item in photos)


def test_photo_library_api_exposes_metadata_and_download(monkeypatch, tmp_path):
    from main import app

    archived = tmp_path / "01_photo.jpg"
    _make_jpg(archived, "purple")

    batch = {
        "id": "batch-1",
        "source_chat_id": "123",
        "target_chat_id": "-1001",
        "code": "25.3251_norma_ifsh",
        "model_code": "25.3251",
        "category": None,
        "caption_message_id": 301,
        "photo_count": 1,
        "created_at": "2026-03-20T12:00:00+00:00",
    }
    photo = {
        "id": "photo-1",
        "batch_id": "batch-1",
        "photo_index": 1,
        "source_file_id": "file-a",
        "target_message_id": 101,
        "archive_path": str(archived),
        "filename": archived.name,
        "created_at": "2026-03-20T12:00:00+00:00",
        "code": "25.3251_norma_ifsh",
        "model_code": "25.3251",
        "category": None,
        "source_chat_id": "123",
        "target_chat_id": "-1001",
        "caption_message_id": 301,
    }

    monkeypatch.setattr("main.photo_library_repo.list_models", lambda: [{"model_code": "25.3251", "batch_count": 1, "photo_count": 1, "latest_batch_at": batch["created_at"]}])
    monkeypatch.setattr("main.photo_library_repo.list_batches", lambda **kwargs: [batch])
    monkeypatch.setattr("main.photo_library_repo.get_batch", lambda batch_id: batch if batch_id == "batch-1" else None)
    monkeypatch.setattr("main.photo_library_repo.list_photos", lambda **kwargs: [photo])
    monkeypatch.setattr("main.photo_library_repo.get_photo", lambda photo_id: photo if photo_id == "photo-1" else None)

    with TestClient(app) as client:
        models_resp = client.get("/api/photo-library/models")
        batch_resp = client.get("/api/photo-library/batches/batch-1")
        photo_resp = client.get("/api/photo-library/photos/photo-1")
        download_resp = client.get("/api/photo-library/photos/photo-1/download")

    assert models_resp.status_code == 200
    assert models_resp.json()["items"][0]["model_code"] == "25.3251"
    assert batch_resp.status_code == 200
    assert batch_resp.json()["batch"]["id"] == "batch-1"
    assert photo_resp.status_code == 200
    assert photo_resp.json()["download_url"].endswith("/api/photo-library/photos/photo-1/download")
    assert download_resp.status_code == 200
    assert download_resp.headers["content-type"].startswith("image/jpeg")
