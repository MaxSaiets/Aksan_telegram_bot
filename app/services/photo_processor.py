"""Resize and compress photos for Telegram delivery."""
from __future__ import annotations

import io
import re
from pathlib import Path

from PIL import Image, ImageOps

from app.utils.file_manager import get_temp_path

MAX_WIDTH = 600
MAX_HEIGHT = 900
INITIAL_QUALITY = 82
MIN_QUALITY = 45
TARGET_BYTES = 250 * 1024


def sanitize_code(code: str) -> str:
    """Convert user text into a filename-safe value."""
    cleaned = re.sub(r"\s+", "_", code.strip())
    cleaned = re.sub(r'[<>:"/\\\\|?*]+', "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("._")
    return cleaned or "photo"


def process_photo(source_path: Path, code: str, index: int) -> Path:
    """
    Convert an image to a lightweight JPG.

    The photo is scaled to fit inside 600x900 without upscaling.
    """
    out_path = get_temp_path(".jpg")
    out_path = out_path.with_name(f"{sanitize_code(code)}_{index:02d}.jpg")

    with Image.open(source_path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.Resampling.LANCZOS)

        quality = INITIAL_QUALITY
        encoded = _encode_jpeg(image, quality)
        while len(encoded) > TARGET_BYTES and quality > MIN_QUALITY:
            quality -= 7
            encoded = _encode_jpeg(image, quality)

    out_path.write_bytes(encoded)
    return out_path


def _encode_jpeg(image: Image.Image, quality: int) -> bytes:
    buffer = io.BytesIO()
    image.save(
        buffer,
        format="JPEG",
        quality=quality,
        optimize=True,
        progressive=True,
    )
    return buffer.getvalue()
