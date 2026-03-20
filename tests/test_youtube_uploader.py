from pathlib import Path

from config import settings


def test_delete_from_youtube_returns_false_when_token_missing_delete_scope(tmp_path, monkeypatch):
    from app.services.youtube_uploader import delete_from_youtube

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "USE_MOCKS", False)
    Path("token.json").write_text(
        '{"token": "abc", "refresh_token": "def", "token_uri": "https://oauth2.googleapis.com/token", "client_id": "cid", "client_secret": "secret", "scopes": ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]}',
        encoding="utf-8",
    )

    assert delete_from_youtube("https://www.youtube.com/watch?v=test123") is False