"""Helpers for extracting model codes, categories, and sizes."""
from __future__ import annotations

import re

_MODEL_RE = re.compile(r"(?<![.\d])(\d+(?:\.\d+)+)(?![.\d])")
_SIZE_RE = re.compile(r"_(\d{2})(?:\(|_|$)")

_CATEGORY_PATTERNS: list[tuple[str, str]] = [
    ("супер ботал", "супер ботал"),
    ("суперботал", "супер ботал"),
    ("супер бот", "супер ботал"),
    ("супербот", "супер ботал"),
    ("ботал", "ботал"),
    ("бот", "ботал"),
    ("норма", "норма"),
    ("норм", "норма"),
]

_BASE_CATEGORY_SIZES: dict[str, set[int]] = {
    "норма": {40, 42, 44},
    "ботал": {50, 52, 54},
    "супер ботал": {56, 58, 60},
}


def extract_model_code(text: str) -> str | None:
    match = _MODEL_RE.search(text or "")
    return match.group(1) if match else None


def extract_category(text: str) -> str | None:
    lowered = (text or "").lower().replace("-", " ")
    for pattern, canonical in _CATEGORY_PATTERNS:
        if pattern in lowered:
            return canonical
    return None


def parse_video_caption(text: str) -> dict[str, str | None]:
    return {
        "model": extract_model_code(text),
        "category": extract_category(text),
    }


def extract_variant_size(article: str) -> int | None:
    match = _SIZE_RE.search(article or "")
    if match:
        return int(match.group(1))
    return None


def allowed_sizes_for_category(category: str | None, available_sizes: set[int]) -> set[int]:
    if not category:
        return set()

    allowed = set(_BASE_CATEGORY_SIZES.get(category, set()))

    # "Норма" may include 46 if the model has 42/44 and no 40.
    if category == "норма" and 40 not in available_sizes and {42, 44}.issubset(available_sizes):
        allowed.add(46)

    return allowed


def variant_matches_category(article: str, category: str | None, available_sizes: set[int]) -> bool:
    size = extract_variant_size(article)
    if size is None:
        return False
    return size in allowed_sizes_for_category(category, available_sizes)
