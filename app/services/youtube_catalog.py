"""
Fetch all videos from the YouTube channel and parse titles.

Title parsing extracts:
  - model code: numeric pattern like "26.2873" or "5.52.2554"
  - size category: норма / ботал / супер ботал / великий ботал / мега ботал

USE_MOCKS=true  → returns hardcoded mock videos (no API call)
USE_MOCKS=false → uses YouTube Data API v3 with existing OAuth2 token.json
"""
import re
import json
from pathlib import Path

from config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Order matters — longer/specific phrases first, then shorter ones
# Each entry: (pattern_to_search, canonical_name)
_CATEGORIES = [
    ("супер ботал", "супер ботал"),
    ("великий ботал", "великий ботал"),
    ("мега ботал", "мега ботал"),
    ("ботал", "ботал"),
    ("бот",   "ботал"),   # abbreviation used in video titles
    ("норма", "норма"),
    ("норм",  "норма"),   # abbreviation
]

# Numeric model code: "26.2873", "5.52.2554"
# No \b at boundaries — titles often have model directly before/after "_"
_MODEL_RE = re.compile(r'(?<![.\d])(\d+(?:\.\d+)+)(?![.\d])')

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
        "title": "26.2630_норма",
        "url": "https://www.youtube.com/watch?v=mock003",
        "model": "26.2630",
        "category": "норма",
        "published_at": "2025-10-03T10:00:00Z",
    },
]


def parse_title(title: str) -> dict:
    """
    Extract model code and size category from a YouTube video title.

    Title formats seen in practice:
      "26.2851_норма_костюм_замш"   → {model: "26.2851", category: "норма"}
      "26.2851_бот_костюм_замш"     → {model: "26.2851", category: "ботал"}
      "26.2861_супер ботал"         → {model: "26.2861", category: "супер ботал"}
      "Aksan 26.2861 Норма"         → {model: "26.2861", category: "норма"}

    Strategy:
      1. Model — try splitting by "_" first (most titles start with model code),
         fall back to regex on the full title.
      2. Category — search through title parts, handle abbreviations.
    """
    title_lower = title.lower()
    parts = title_lower.split("_")

    # --- Model extraction ---
    # First part before "_" is usually the model code
    model = None
    first_part = parts[0].strip()
    first_match = _MODEL_RE.findall(first_part)
    if first_match:
        model = first_match[0]
    else:
        # Fallback: scan full title
        all_matches = _MODEL_RE.findall(title)
        if all_matches:
            model = all_matches[0]

    # --- Category extraction ---
    category = None
    for pattern, canonical in _CATEGORIES:
        # Check each "_"-separated part (exact match or substring)
        for part in parts:
            if pattern in part.strip():
                category = canonical
                break
        if category:
            break

    return {"model": model, "category": category}


def fetch_channel_videos() -> list[dict]:
    """
    Fetch all uploaded videos from YOUTUBE_CHANNEL_ID.

    Returns list of dicts:
      video_id, title, url, model, category, published_at
    """
    if settings.USE_MOCKS:
        logger.info("[MOCK YouTube] Returning %d mock videos", len(_MOCK_VIDEOS))
        return list(_MOCK_VIDEOS)

    return _real_fetch_videos()


def _get_youtube_service():
    """Build authenticated YouTube service from stored token.json."""
    import google.oauth2.credentials
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request

    SCOPES = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly",
    ]

    token_file = Path("token.json")
    if not token_file.exists():
        raise RuntimeError("token.json not found — run scripts/youtube_auth.py first")

    creds_data = json.loads(token_file.read_text(encoding="utf-8"))
    creds = google.oauth2.credentials.Credentials.from_authorized_user_info(
        creds_data, SCOPES
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_file.write_text(creds.to_json(), encoding="utf-8")
        logger.info("YouTube token refreshed and saved")

    return build("youtube", "v3", credentials=creds)


def _real_fetch_videos() -> list[dict]:
    youtube = _get_youtube_service()

    # Step 1: get the uploads playlist ID for the channel
    ch_resp = youtube.channels().list(
        part="contentDetails",
        id=settings.YOUTUBE_CHANNEL_ID,
    ).execute()

    items = ch_resp.get("items", [])
    if not items:
        logger.error("YouTube channel not found: %s", settings.YOUTUBE_CHANNEL_ID)
        return []

    playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    logger.info("YouTube uploads playlist: %s", playlist_id)

    # Step 2: paginate through all playlist items
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
