"""Preview or apply SEO metadata updates to existing videos on the authenticated channel."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.youtube_uploader import (
    list_channel_upload_video_ids,
    prepare_existing_video_metadata,
    prepare_existing_videos_metadata,
    update_existing_video_metadata,
    update_existing_videos_metadata,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update YouTube descriptions and tags without changing video titles."
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--video-id", action="append", help="One YouTube video id; may be repeated.")
    selection.add_argument("--all", action="store_true", help="Select every upload on the authenticated channel.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes. Without this flag the script only previews them.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    video_ids = list_channel_upload_video_ids() if args.all else args.video_id
    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"{mode}: {len(video_ids)} video(s)")

    metadata_items = (
        update_existing_videos_metadata(video_ids)
        if args.apply and args.all
        else prepare_existing_videos_metadata(video_ids)
        if not args.apply and args.all
        else [
            update_existing_video_metadata(video_id)
            if args.apply
            else prepare_existing_video_metadata(video_id)
            for video_id in video_ids
        ]
    )
    for metadata in metadata_items:
        print(f"{metadata.video_id}: {metadata.title}")
        print(metadata.description)
        print(f"Tags ({len(metadata.tags)}): {', '.join(metadata.tags)}")
        print()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"YouTube metadata update failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
