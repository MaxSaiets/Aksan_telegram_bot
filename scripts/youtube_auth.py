"""
One-time YouTube OAuth2 authorization script.
Run once on the server to generate token.json.
After that the Celery worker reuses the saved token automatically.

Usage:
    python scripts/youtube_auth.py
"""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.youtube_uploader import YOUTUBE_AUTH_SCOPES
from config import settings


def main():
    secrets_file = Path(settings.YOUTUBE_CLIENT_SECRETS_FILE)
    if not secrets_file.exists():
        print(f"ERROR: {secrets_file} not found.")
        print("Download it from Google Cloud Console -> APIs & Services -> Credentials")
        sys.exit(1)

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), YOUTUBE_AUTH_SCOPES)
    creds = flow.run_local_server(port=0)

    token_file = Path("token.json")
    token_file.write_text(creds.to_json(), encoding="utf-8")
    print(f"Token saved to {token_file.resolve()}")
    print("You can now run the bot — uploads and deletions will use this token.")


if __name__ == "__main__":
    main()