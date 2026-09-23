from pathlib import Path
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
