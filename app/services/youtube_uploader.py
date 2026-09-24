"""
Upload videos to YouTube.
- USE_MOCKS=true  -> returns a fake YouTube URL instantly
- USE_MOCKS=false -> uses YouTube Data API v3 with OAuth2
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.services.youtube_metadata import build_youtube_metadata
from app.utils.logger import get_logger
from config import settings

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

YOUTUBE_DELETE_SCOPES = [
    "https://www.googleapis.com/auth/youtube",
]
YOUTUBE_AUTH_SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


@dataclass(frozen=True)
class YouTubeMetadataUpdate:
    """The metadata applied to one existing YouTube video."""

    video_id: str
    title: str
    description: str
    tags: list[str]


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


def _authorized_youtube_service():
    """Create a YouTube client from the stored OAuth grant and refresh it if needed."""
    token_file = _token_file()
    if not token_file.exists():
        raise FileNotFoundError(f"token.json not found at {token_file}")

    import google.oauth2.credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = google.oauth2.credentials.Credentials.from_authorized_user_info(
        _load_token_data(token_file)
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_file.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def _existing_video_snippet(youtube, video_id: str) -> dict:
    response = youtube.videos().list(part="snippet", id=video_id).execute()
    items = response.get("items", [])
    if not items:
        raise ValueError(f"YouTube video not found or not accessible: {video_id}")
    return dict(items[0].get("snippet") or {})


def _existing_video_snippets(youtube, video_ids: list[str]) -> dict[str, dict]:
    """Read snippets in the largest YouTube API batch supported by videos.list."""
    snippets: dict[str, dict] = {}
    for start in range(0, len(video_ids), 50):
        response = youtube.videos().list(
            part="snippet",
            id=",".join(video_ids[start:start + 50]),
        ).execute()
        snippets.update({
            item["id"]: dict(item.get("snippet") or {})
            for item in response.get("items", [])
        })
    missing = [video_id for video_id in video_ids if video_id not in snippets]
    if missing:
        raise ValueError(f"YouTube videos not found or not accessible: {', '.join(missing)}")
    return snippets


def _metadata_for_snippet(
    video_id: str,
    snippet: dict,
    require_ai: bool = False,
) -> YouTubeMetadataUpdate:
    title = str(snippet.get("title") or "").strip()
    if not title:
        raise ValueError(f"YouTube video has no title: {video_id}")
    metadata = build_youtube_metadata(
        title,
        list(snippet.get("tags") or []),
        require_ai=require_ai,
    )
    return YouTubeMetadataUpdate(
        video_id=video_id,
        title=title,
        description=metadata.description,
        tags=metadata.tags,
    )


def prepare_existing_video_metadata(video_id: str) -> YouTubeMetadataUpdate:
    """Read an existing video and calculate its new SEO metadata without writing."""
    youtube = _authorized_youtube_service()
    return _metadata_for_snippet(video_id, _existing_video_snippet(youtube, video_id))


def prepare_existing_videos_metadata(video_ids: list[str]) -> list[YouTubeMetadataUpdate]:
    """Preview metadata for many videos with batched reads and no writes."""
    youtube = _authorized_youtube_service()
    snippets = _existing_video_snippets(youtube, video_ids)
    return [_metadata_for_snippet(video_id, snippets[video_id]) for video_id in video_ids]


def update_existing_video_metadata(
    video_id: str,
    require_ai: bool = False,
) -> YouTubeMetadataUpdate:
    """Update description/tags only while preserving the existing title and snippet settings."""
    youtube = _authorized_youtube_service()
    snippet = _existing_video_snippet(youtube, video_id)
    metadata = _metadata_for_snippet(video_id, snippet, require_ai=require_ai)
    updated_snippet = {
        "title": metadata.title,
        "description": metadata.description,
        "tags": metadata.tags,
        "categoryId": str(snippet.get("categoryId") or "22"),
        "defaultLanguage": str(snippet.get("defaultLanguage") or settings.YOUTUBE_DEFAULT_LANGUAGE),
    }
    if snippet.get("defaultAudioLanguage"):
        updated_snippet["defaultAudioLanguage"] = snippet["defaultAudioLanguage"]

    youtube.videos().update(
        part="snippet",
        body={"id": video_id, "snippet": updated_snippet},
    ).execute()
    logger.info("Updated YouTube metadata: video_id=%s title=%s", video_id, metadata.title)
    return metadata


def update_existing_videos_metadata(video_ids: list[str]) -> list[YouTubeMetadataUpdate]:
    """Apply metadata to many videos, batching reads while preserving every title."""
    youtube = _authorized_youtube_service()
    snippets = _existing_video_snippets(youtube, video_ids)
    results: list[YouTubeMetadataUpdate] = []
    for video_id in video_ids:
        snippet = snippets[video_id]
        metadata = _metadata_for_snippet(video_id, snippet)
        if (
            snippet.get("description", "") == metadata.description
            and list(snippet.get("tags") or []) == metadata.tags
        ):
            logger.info("YouTube metadata already current: video_id=%s", video_id)
            results.append(metadata)
            continue
        updated_snippet = {
            "title": metadata.title,
            "description": metadata.description,
            "tags": metadata.tags,
            "categoryId": str(snippet.get("categoryId") or "22"),
            "defaultLanguage": str(snippet.get("defaultLanguage") or settings.YOUTUBE_DEFAULT_LANGUAGE),
        }
        if snippet.get("defaultAudioLanguage"):
            updated_snippet["defaultAudioLanguage"] = snippet["defaultAudioLanguage"]
        youtube.videos().update(
            part="snippet",
            body={"id": video_id, "snippet": updated_snippet},
        ).execute()
        results.append(metadata)
        logger.info("Updated YouTube metadata: video_id=%s title=%s", video_id, metadata.title)
    return results


def list_channel_upload_video_ids() -> list[str]:
    """Return every video id from the authenticated channel's uploads playlist."""
    youtube = _authorized_youtube_service()
    channels = youtube.channels().list(part="contentDetails", mine=True).execute()
    channel_items = channels.get("items", [])
    if not channel_items:
        raise ValueError("No YouTube channel is available for the current token")

    uploads_id = channel_items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    video_ids: list[str] = []
    page_token = None
    while True:
        response = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_id,
            maxResults=50,
            pageToken=page_token,
        ).execute()
        video_ids.extend(
            item["contentDetails"]["videoId"]
            for item in response.get("items", [])
            if item.get("contentDetails", {}).get("videoId")
        )
        page_token = response.get("nextPageToken")
        if not page_token:
            return video_ids


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

        # Reuse the exact grant saved by OAuth. Passing a narrower scope list
        # during refresh can make Google's token endpoint reject it as invalid_scope.
        creds = google.oauth2.credentials.Credentials.from_authorized_user_info(creds_data)
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
    tags: list[str] | None = None,
    publish_at: datetime | None = None,
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
        # Keep the original OAuth grant intact for refreshes. The token already
        # carries every scope needed for upload, delete, and channel reads.
        creds = google.oauth2.credentials.Credentials.from_authorized_user_info(creds_data)
    else:
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), YOUTUBE_AUTH_SCOPES)
        creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json(), encoding="utf-8")
        logger.info("YouTube token saved to %s", token_file)

    youtube = build("youtube", "v3", credentials=creds)
    status = {"privacyStatus": "public"}
    if publish_at:
        if publish_at.tzinfo is None:
            raise ValueError("publish_at must include a timezone")
        status = {
            "privacyStatus": "private",
            "publishAt": publish_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

    request_body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "22",
            "defaultLanguage": settings.YOUTUBE_DEFAULT_LANGUAGE,
        },
        "status": status,
    }
    if tags:
        request_body["snippet"]["tags"] = tags

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
