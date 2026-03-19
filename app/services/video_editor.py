"""
Video editing: overlay text caption onto a video using FFmpeg.
Always uses real FFmpeg processing (FFmpeg is available on this machine).
USE_MOCKS only affects YouTube / Storage / SalesDrive / Rozetka.
"""
import shutil
import sys
from pathlib import Path

from app.utils.logger import get_logger
from app.utils.file_manager import get_temp_path

logger = get_logger(__name__)


def _find_font() -> str:
    """Find a bold/regular TTF font that works on Windows and Linux."""
    candidates = [
        # Windows
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\verdana.ttf",
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return ""  # ffmpeg will use its built-in font if path is empty


def overlay_text(input_path: Path, text: str) -> Path:
    """
    Return a copy of the video ready for broadcast.
    No text overlay — video goes as-is.
    """
    output_path = get_temp_path("_captioned.mp4")
    shutil.copy2(input_path, output_path)
    logger.info("Video copied without overlay: %s", output_path.name)
    return output_path
