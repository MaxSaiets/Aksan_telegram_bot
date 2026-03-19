"""
Upload videos to YouTube.
- USE_MOCKS=true  -> returns a fake YouTube URL instantly
- USE_MOCKS=false -> uses YouTube Data API v3 with OAuth2
"""
from pathlib import Path

from config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


def delete_from_youtube(youtube_url: str) -> bool:
    """
    Delete a video from YouTube by its URL.
    Returns True if deleted, False if failed or not configured.
    """
    if settings.USE_MOCKS:
        logger.info("[MOCK YouTube] Pretending to delete: %s", youtube_url)
        return True

    import json
    import re

    match = re.search(r"[?&]v=([^&]+)", youtube_url or "")
    if not match:
        logger.warning("Cannot extract video ID from URL: %s", youtube_url)
        return False

    video_id = match.group(1)
    token_file = Path("token.json")
    if not token_file.exists():
        logger.warning("token.json not found - cannot delete from YouTube")
        return False

    try:
        import google.oauth2.credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        scopes = [
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube",
        ]

        creds_data = json.loads(token_file.read_text())
        creds = google.oauth2.credentials.Credentials.from_authorized_user_info(creds_data, scopes)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_file.write_text(creds.to_json())

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

    import json

    import google.oauth2.credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    token_file = Path("token.json")
    secrets_file = Path(settings.YOUTUBE_CLIENT_SECRETS_FILE)

    if not token_file.exists() and not secrets_file.exists():
        logger.warning(
            "YouTube not configured (token.json and %s not found) - skipping upload",
            settings.YOUTUBE_CLIENT_SECRETS_FILE,
        )
        return "https://youtube.com/not-configured"

    if token_file.exists():
        creds_data = json.loads(token_file.read_text())
        creds = google.oauth2.credentials.Credentials.from_authorized_user_info(creds_data, scopes)
    else:
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), scopes)
        creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json())
        logger.info("YouTube token saved to token.json")

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
