"""
Fetch all videos from the YouTube channel and parse titles.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.services.sku_parser import parse_video_caption
from app.utils.logger import get_logger
from config import settings

logger = get_logger(__name__)

_MOCK_VIDEOS = [
    {
        "video_id": "mock001",
        "title": "26.2873_норма",
        "url": "https://www.youtube.com/watch?v=mock001",
        "model": "26.2873",
        "category": "норма",
        "published_at": "2025-10-01T10:00:00Z",
    },
    {
        "video_id": "mock002",
        "title": "26.2861_ботал",
        "url": "https://www.youtube.com/watch?v=mock002",
        "model": "26.2861",
        "category": "ботал",
        "published_at": "2025-10-02T10:00:00Z",
    },
    {
        "video_id": "mock003",
        "title": "26.2630_супер ботал",
        "url": "https://www.youtube.com/watch?v=mock003",
        "model": "26.2630",
        "category": "супер ботал",
        "published_at": "2025-10-03T10:00:00Z",
    },
]


def parse_title(title: str) -> dict[str, str | None]:
    """Extract model code and size category from a YouTube title."""
    return parse_video_caption(title)


def fetch_channel_videos() -> list[dict]:
    """
    Fetch all uploaded videos from YOUTUBE_CHANNEL_ID.

    Returns list of dicts with:
      video_id, title, url, model, category, published_at
    """
    if settings.USE_MOCKS:
        logger.info("[MOCK YouTube] Returning %d mock videos", len(_MOCK_VIDEOS))
        return list(_MOCK_VIDEOS)

    return _real_fetch_videos()


def _get_youtube_service():
    """Build authenticated YouTube service from stored token.json."""
    import google.oauth2.credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    scopes = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly",
    ]

    token_file = Path("token.json")
    if not token_file.exists():
        raise RuntimeError("token.json not found - run scripts/youtube_auth.py first")

    creds_data = json.loads(token_file.read_text(encoding="utf-8"))
    creds = google.oauth2.credentials.Credentials.from_authorized_user_info(
        creds_data,
        scopes,
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_file.write_text(creds.to_json(), encoding="utf-8")
        logger.info("YouTube token refreshed and saved")

    return build("youtube", "v3", credentials=creds)


def _real_fetch_videos() -> list[dict]:
    youtube = _get_youtube_service()

    channel_resp = youtube.channels().list(
        part="contentDetails",
        id=settings.YOUTUBE_CHANNEL_ID,
    ).execute()

    items = channel_resp.get("items", [])
    if not items:
        logger.error("YouTube channel not found: %s", settings.YOUTUBE_CHANNEL_ID)
        return []

    playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    logger.info("YouTube uploads playlist: %s", playlist_id)

    videos: list[dict] = []
    next_token = None

    while True:
        kwargs: dict = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": 50,
        }
        if next_token:
            kwargs["pageToken"] = next_token

        resp = youtube.playlistItems().list(**kwargs).execute()

        for item in resp.get("items", []):
            snippet = item["snippet"]
            video_id = snippet["resourceId"]["videoId"]
            title = snippet.get("title", "")
            published_at = snippet.get("publishedAt", "")
            parsed = parse_title(title)

            videos.append({
                "video_id": video_id,
                "title": title,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "model": parsed["model"],
                "category": parsed["category"],
                "published_at": published_at,
            })

        next_token = resp.get("nextPageToken")
        if not next_token:
            break

    logger.info("YouTube channel: fetched %d videos total", len(videos))
    return videos