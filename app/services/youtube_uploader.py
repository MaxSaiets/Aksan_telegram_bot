"""
Upload videos to YouTube.
- USE_MOCKS=true  -> returns a fake YouTube URL instantly
- USE_MOCKS=false -> uses YouTube Data API v3 with OAuth2
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.utils.logger import get_logger
from config import settings

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

YOUTUBE_UPLOAD_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
YOUTUBE_DELETE_SCOPES = [
    "https://www.googleapis.com/auth/youtube",
]
YOUTUBE_AUTH_SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def _project_file(path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else _PROJECT_ROOT / path


def _token_file() -> Path:
    return _project_file("token.json")


def _extract_video_id(youtube_url: str) -> str | None:
    parsed = urlparse((youtube_url or "").strip())

    if not parsed.scheme and youtube_url:
        text = youtube_url.strip()
        if len(text) >= 6 and "/" not in text and "?" not in text:
            return text
        return None

    if parsed.netloc in {"youtu.be", "www.youtu.be"}:
        return parsed.path.strip("/") or None

    if parsed.path == "/watch":
        return parse_qs(parsed.query).get("v", [None])[0]

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] in {"shorts", "live", "embed"}:
        return parts[1]

    return parse_qs(parsed.query).get("v", [None])[0]


def _load_token_data(token_file: Path) -> dict:
    return json.loads(token_file.read_text(encoding="utf-8"))


def _missing_scopes(creds_data: dict, required_scopes: list[str]) -> list[str]:
    token_scopes = set(creds_data.get("scopes") or [])
    if not token_scopes:
        return []
    return [scope for scope in required_scopes if scope not in token_scopes]


def delete_from_youtube(youtube_url: str) -> bool:
    """
    Delete a video from YouTube by its URL.
    Returns True if deleted, False if failed or not configured.
    """
    if settings.USE_MOCKS:
        logger.info("[MOCK YouTube] Pretending to delete: %s", youtube_url)
        return True

    video_id = _extract_video_id(youtube_url)
    if not video_id:
        logger.warning("Cannot extract video ID from URL: %s", youtube_url)
        return False

    token_file = _token_file()
    if not token_file.exists():
        logger.warning("token.json not found at %s - cannot delete from YouTube", token_file)
        return False

    try:
        creds_data = _load_token_data(token_file)
        missing = _missing_scopes(creds_data, YOUTUBE_DELETE_SCOPES)
        if missing:
            logger.error(
                "token.json at %s is missing delete scopes %s. Re-run scripts/youtube_auth.py to regenerate token.json",
                token_file,
                missing,
            )
            return False

        import google.oauth2.credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = google.oauth2.credentials.Credentials.from_authorized_user_info(
            creds_data,
            YOUTUBE_AUTH_SCOPES,
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_file.write_text(creds.to_json(), encoding="utf-8")

        youtube = build("youtube", "v3", credentials=creds)
        youtube.videos().delete(id=video_id).execute()
        logger.info("Deleted from YouTube: video_id=%s", video_id)
        return True
    except Exception as exc:
        logger.error("Failed to delete from YouTube (%s): %s", video_id, exc)
        return False


def upload_to_youtube(
    video_path: Path,
    title: str,
    description: str = "",
    on_progress=None,
) -> str:
    """
    Upload video_path to YouTube and return the watch URL.
    Blocking - runs inside a Celery worker.
    """
    if settings.USE_MOCKS:
        fake_id = "dQw4w9WgXcQ"
        url = f"https://www.youtube.com/watch?v={fake_id}"
        logger.info("[MOCK YouTube] Pretending to upload '%s' -> %s", title, url)
        return url

    import google.oauth2.credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    token_file = _token_file()
    secrets_file = _project_file(settings.YOUTUBE_CLIENT_SECRETS_FILE)

    if not token_file.exists() and not secrets_file.exists():
        logger.warning(
            "YouTube not configured (token.json and %s not found) - skipping upload",
            secrets_file,
        )
        return "https://youtube.com/not-configured"

    if token_file.exists():
        creds_data = _load_token_data(token_file)
        creds = google.oauth2.credentials.Credentials.from_authorized_user_info(
            creds_data,
            YOUTUBE_UPLOAD_SCOPES,
        )
    else:
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), YOUTUBE_AUTH_SCOPES)
        creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json(), encoding="utf-8")
        logger.info("YouTube token saved to %s", token_file)

    youtube = build("youtube", "v3", credentials=creds)
    request_body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "22",
        },
        "status": {"privacyStatus": "public"},
    }

    media = MediaFileUpload(str(video_path), chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(
        part="snippet,status",
        body=request_body,
        media_body=media,
    )

    response = None
    last_reported_percent = -1
    while response is None:
        status, response = request.next_chunk()
        if status is None:
            continue
        percent = int(status.progress() * 100)
        if on_progress and percent >= last_reported_percent + 10:
            last_reported_percent = percent
            on_progress(percent)

    video_id = response["id"]
    url = f"https://www.youtube.com/watch?v={video_id}"
    logger.info("Uploaded to YouTube: %s -> %s", video_path.name, url)
    return url
