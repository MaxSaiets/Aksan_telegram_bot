"""Preview or apply SEO metadata updates to existing videos on the authenticated channel."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.youtube_uploader import (
    list_channel_upload_video_ids,
    prepare_existing_video_metadata,
    prepare_existing_videos_metadata,
    update_existing_video_metadata,
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
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=5.0,
        help="Pause between AI updates when applying a batch (default: 5 seconds).",
    )
    parser.add_argument(
        "--checkpoint-file",
        default="tmp/youtube-ai-metadata-progress.json",
        help="Ignored local checkpoint for successfully AI-updated video IDs.",
    )
    return parser.parse_args()


def _load_checkpoint(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")))


def _save_checkpoint(path: Path, video_ids: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(video_ids), ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = _parse_args()
    video_ids = list_channel_upload_video_ids() if args.all else args.video_id
    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"{mode}: {len(video_ids)} video(s)")

    if not args.apply:
        metadata_items = prepare_existing_videos_metadata(video_ids) if args.all else [
            prepare_existing_video_metadata(video_id) for video_id in video_ids
        ]
    else:
        checkpoint_path = PROJECT_ROOT / args.checkpoint_file
        completed = _load_checkpoint(checkpoint_path)
        pending = [video_id for video_id in video_ids if video_id not in completed]
        print(f"Pending strict AI updates: {len(pending)}")
        metadata_items = []
        for index, video_id in enumerate(pending, start=1):
            metadata = update_existing_video_metadata(video_id, require_ai=True)
            metadata_items.append(metadata)
            completed.add(video_id)
            _save_checkpoint(checkpoint_path, completed)
            print(f"[{index}/{len(pending)}] AI updated: {metadata.title}")
            if index < len(pending):
                time.sleep(max(args.delay_seconds, 0))
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
