"""Build concise, search-friendly metadata without changing video titles."""
from __future__ import annotations

from dataclasses import dataclass
import re

from app.services.sku_parser import parse_video_caption
from config import settings


_CATEGORY_COPY = {
    "норма": "Розмірна група: норма (40–44, за наявності може бути 46).",
    "ботал": "Розмірна група: ботал (50–54).",
    "супер ботал": "Розмірна група: супер ботал (56–60).",
}
_IGNORED_TERMS = {
    "aksan",
    "аксан",
    "норма",
    "норм",
    "ботал",
    "бот",
    "супер",
    "super",
}
_TAG_BUDGET = 450


@dataclass(frozen=True)
class YouTubeMetadata:
    """Metadata derived from a caption while preserving the original title."""

    title: str
    description: str
    tags: list[str]


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        clean = " ".join((item or "").split()).strip()
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def _product_terms(caption: str, model: str | None) -> list[str]:
    terms = re.findall(r"[^_\s]+", caption or "")
    result: list[str] = []

    for term in terms:
        normalized = term.strip(".,;:!?()[]{}\"").casefold()
        if not normalized or normalized == (model or "").casefold():
            continue
        if normalized in _IGNORED_TERMS:
            continue
        if normalized.isdigit():
            continue
        result.append(term.strip(".,;:!?()[]{}\""))

    return _unique(result)[:4]


def _configured_extra_tags() -> list[str]:
    return [tag.strip() for tag in settings.YOUTUBE_EXTRA_TAGS.split(",") if tag.strip()]


def _within_tag_budget(tags: list[str]) -> list[str]:
    result: list[str] = []
    total = 0
    for tag in _unique(tags):
        projected = total + len(tag) + (1 if result else 0)
        if projected > _TAG_BUDGET:
            break
        result.append(tag)
        total = projected
    return result


def build_youtube_metadata(caption: str) -> YouTubeMetadata:
    """Create description and tags while keeping the supplied title unchanged."""
    title = (caption or "").strip()
    parsed = parse_video_caption(title)
    model = parsed["model"]
    category = parsed["category"]
    brand = settings.YOUTUBE_BRAND_NAME.strip() or "Aksan"
    product_terms = _product_terms(title, model)

    product_name = " ".join(product_terms)
    if product_name and model:
        lead = f"{product_name.capitalize()} {brand} — модель {model}."
    elif model:
        lead = f"Жіночий одяг {brand} — модель {model}."
    else:
        lead = f"Новинка жіночого одягу від {brand}."

    description_lines = [lead]
    if category in _CATEGORY_COPY:
        description_lines.append(_CATEGORY_COPY[category])
    description_lines.append(f"Дивіться відеоогляд моделі та інші новинки {brand} на каналі.")

    footer = settings.YOUTUBE_DESCRIPTION_FOOTER.strip()
    if footer:
        description_lines.extend(["", footer])

    tags = _within_tag_budget([
        brand,
        "Аксан",
        model or "",
        f"модель {model}" if model else "",
        *product_terms,
        "жіночий одяг",
        "одяг Україна",
        category or "",
        *_configured_extra_tags(),
    ])

    return YouTubeMetadata(
        title=title,
        description="\n".join(description_lines),
        tags=tags,
    )
