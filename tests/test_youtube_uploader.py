from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock

from config import settings


def test_delete_from_youtube_returns_false_when_token_missing_delete_scope(tmp_path, monkeypatch):
    import app.services.youtube_uploader as youtube_uploader

    monkeypatch.setattr(settings, "USE_MOCKS", False)
    token_file = tmp_path / "token.json"
    token_file.write_text(
        '{"token": "abc", "refresh_token": "def", "token_uri": "https://oauth2.googleapis.com/token", "client_id": "cid", "client_secret": "secret", "scopes": ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(youtube_uploader, "_token_file", lambda: token_file)

    assert youtube_uploader.delete_from_youtube("https://www.youtube.com/watch?v=test123") is False


def test_upload_reuses_scopes_saved_in_token(tmp_path, monkeypatch, temp_video):
    import google.oauth2.credentials
    import googleapiclient.discovery
    import googleapiclient.http
    import app.services.youtube_uploader as youtube_uploader

    monkeypatch.setattr(settings, "USE_MOCKS", False)
    token_file = tmp_path / "token.json"
    token_file.write_text(
        '{"token": "abc", "refresh_token": "def", "token_uri": "https://oauth2.googleapis.com/token", "client_id": "cid", "client_secret": "secret", "scopes": ["https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(youtube_uploader, "_token_file", lambda: token_file)

    requested_scopes = []
    creds = MagicMock()
    creds.expired = False
    creds.refresh_token = None

    def from_authorized_user_info(data, scopes=None):
        requested_scopes.append(scopes)
        return creds

    request = MagicMock()
    request.next_chunk.return_value = (None, {"id": "uploaded-video"})
    youtube = MagicMock()
    youtube.videos().insert.return_value = request

    monkeypatch.setattr(
        google.oauth2.credentials.Credentials,
        "from_authorized_user_info",
        staticmethod(from_authorized_user_info),
    )
    monkeypatch.setattr(googleapiclient.discovery, "build", lambda *args, **kwargs: youtube)
    monkeypatch.setattr(googleapiclient.http, "MediaFileUpload", lambda *args, **kwargs: object())

    url = youtube_uploader.upload_to_youtube(
        temp_video,
        "26.3048_норма",
        description="Опис моделі",
        tags=["Aksan", "26.3048"],
    )

    assert url == "https://www.youtube.com/watch?v=uploaded-video"
    assert requested_scopes == [None]
    payload = youtube.videos().insert.call_args.kwargs["body"]
    assert payload["snippet"]["description"] == "Опис моделі"
    assert payload["snippet"]["tags"] == ["Aksan", "26.3048"]
    assert payload["snippet"]["defaultLanguage"] == settings.YOUTUBE_DEFAULT_LANGUAGE


def test_upload_schedules_private_video_when_publish_time_is_supplied(tmp_path, monkeypatch, temp_video):
    import google.oauth2.credentials
    import googleapiclient.discovery
    import googleapiclient.http
    import app.services.youtube_uploader as youtube_uploader

    monkeypatch.setattr(settings, "USE_MOCKS", False)
    token_file = tmp_path / "token.json"
    token_file.write_text(
        '{"token":"abc","refresh_token":"def","token_uri":"https://oauth2.googleapis.com/token","client_id":"cid","client_secret":"secret","scopes":["https://www.googleapis.com/auth/youtube"]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(youtube_uploader, "_token_file", lambda: token_file)
    creds = MagicMock()
    creds.expired = False
    creds.refresh_token = None
    request = MagicMock()
    request.next_chunk.return_value = (None, {"id": "scheduled-video"})
    youtube = MagicMock()
    youtube.videos().insert.return_value = request
    monkeypatch.setattr(google.oauth2.credentials.Credentials, "from_authorized_user_info", staticmethod(lambda *_: creds))
    monkeypatch.setattr(googleapiclient.discovery, "build", lambda *args, **kwargs: youtube)
    monkeypatch.setattr(googleapiclient.http, "MediaFileUpload", lambda *args, **kwargs: object())

    youtube_uploader.upload_to_youtube(
        temp_video,
        "26.3057_Aksan_штани_норма_байка",
        publish_at=datetime.fromisoformat("2026-09-24T09:15:00+03:00"),
    )

    status = youtube.videos().insert.call_args.kwargs["body"]["status"]
    assert status == {"privacyStatus": "private", "publishAt": "2026-09-24T06:15:00Z"}


def test_update_existing_video_metadata_preserves_title_and_category(tmp_path, monkeypatch):
    import google.oauth2.credentials
    import googleapiclient.discovery
    import app.services.youtube_uploader as youtube_uploader

    monkeypatch.setattr(settings, "USE_MOCKS", False)
    token_file = tmp_path / "token.json"
    token_file.write_text(
        '{"token": "abc", "refresh_token": "def", "token_uri": "https://oauth2.googleapis.com/token", "client_id": "cid", "client_secret": "secret", "scopes": ["https://www.googleapis.com/auth/youtube"]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(youtube_uploader, "_token_file", lambda: token_file)

    creds = MagicMock()
    creds.expired = False
    creds.refresh_token = None
    youtube = MagicMock()
    youtube.videos().list.return_value.execute.return_value = {
        "items": [{
            "id": "Q7aK1XXbaow",
            "snippet": {
                "title": "26.3048_Aksan_костюм_норма_фрісПолар",
                "description": "Старий опис",
                "tags": ["старий тег"],
                "categoryId": "22",
                "defaultLanguage": "uk",
            },
        }],
    }
    youtube.videos().update.return_value.execute.return_value = {"id": "Q7aK1XXbaow"}

    monkeypatch.setattr(
        google.oauth2.credentials.Credentials,
        "from_authorized_user_info",
        staticmethod(lambda data, scopes=None: creds),
    )
    monkeypatch.setattr(googleapiclient.discovery, "build", lambda *args, **kwargs: youtube)

    result = youtube_uploader.update_existing_video_metadata("Q7aK1XXbaow")

    assert result.video_id == "Q7aK1XXbaow"
    assert result.title == "26.3048_Aksan_костюм_норма_фрісПолар"
    payload = youtube.videos().update.call_args.kwargs["body"]
    assert payload["snippet"]["title"] == "26.3048_Aksan_костюм_норма_фрісПолар"
    assert payload["snippet"]["categoryId"] == "22"
    assert payload["snippet"]["defaultLanguage"] == "uk"
    assert "Розмірна група" not in payload["snippet"]["description"]
    assert payload["snippet"]["description"].count("#") == 5
    assert "жіночий костюм" in payload["snippet"]["tags"]
    assert "старий тег" in payload["snippet"]["tags"]


def test_bulk_metadata_update_skips_videos_that_are_already_current(monkeypatch):
    import app.services.youtube_uploader as youtube_uploader
    from app.services.youtube_metadata import build_youtube_metadata

    title = "26.3057_Aksan_штани_норма_байка"
    current = build_youtube_metadata(title)
    youtube = MagicMock()
    youtube.videos().list.return_value.execute.return_value = {
        "items": [
            {"id": "current", "snippet": {
                "title": title,
                "description": current.description,
                "tags": current.tags,
                "categoryId": "22",
            }},
            {"id": "stale", "snippet": {
                "title": title,
                "description": "старий опис",
                "tags": [],
                "categoryId": "22",
            }},
        ],
    }
    monkeypatch.setattr(youtube_uploader, "_authorized_youtube_service", lambda: youtube)

    youtube_uploader.update_existing_videos_metadata(["current", "stale"])

    assert youtube.videos().update.call_count == 1
    assert youtube.videos().update.call_args.kwargs["body"]["id"] == "stale"
