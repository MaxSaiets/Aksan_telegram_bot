"""Build natural, search-friendly YouTube metadata without changing titles."""
from __future__ import annotations

from dataclasses import dataclass

from config import settings


_TAG_BUDGET = 450
_PRODUCT_KEYWORDS = {
    "костюм": ("жіночий костюм", ["жіночий костюм", "костюм жіночий", "костюми жіночі"]),
    "сукня": ("жіноча сукня", ["жіноча сукня", "сукня жіноча", "сукні жіночі"]),
    "плаття": ("жіноча сукня", ["жіноча сукня", "плаття жіноче", "сукні жіночі"]),
    "блуза": ("жіноча блуза", ["жіноча блуза", "блузка жіноча"]),
    "сорочка": ("жіноча сорочка", ["жіноча сорочка", "сорочка жіноча"]),
    "штани": ("жіночі штани", ["жіночі штани", "штани жіночі"]),
    "спідниця": ("жіноча спідниця", ["жіноча спідниця", "спідниця жіноча"]),
    "жакет": ("жіночий жакет", ["жіночий жакет", "жакет жіночий"]),
    "кардиган": ("жіночий кардиган", ["жіночий кардиган", "кардиган жіночий"]),
    "худі": ("жіноче худі", ["жіноче худі", "худі жіноче"]),
    "светр": ("жіночий светр", ["жіночий светр", "светр жіночий"]),
}


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


def _configured_extra_tags() -> list[str]:
    return [tag.strip() for tag in settings.YOUTUBE_EXTRA_TAGS.split(",") if tag.strip()]


def _product_context(source_text: str) -> tuple[str, list[str], list[str]]:
    """Return human wording, related tags, and exactly five relevant hashtags."""
    lowered = (source_text or "").casefold()
    label = "жіночий одяг"
    product_tags: list[str] = []
    hashtags = ["#Aksan", "#жіночийодяг"]

    for keyword, (candidate_label, candidate_tags) in _PRODUCT_KEYWORDS.items():
        if keyword in lowered:
            label = candidate_label
            product_tags.extend(candidate_tags)
            hashtags.append(f"#{candidate_label.replace(' ', '')}")
            break

    if "трійка" in lowered:
        product_tags.extend(["костюм трійка", "костюм трійка жіночий"])
        hashtags.append("#костюмтрійка")
    if "велюр" in lowered or "велор" in lowered:
        product_tags.extend(["велюровий костюм", "костюм з велюру", "велюр"])
        hashtags.append("#велюровийкостюм")

    hashtags.extend(["#українськийодяг", "#жіночамода", "#новинкиодягу"])
    return label, _unique(product_tags), _unique(hashtags)[:5]


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


def build_youtube_metadata(caption: str, additional_tags: list[str] | None = None) -> YouTubeMetadata:
    """Create description and tags while keeping the supplied title unchanged."""
    title = (caption or "").strip()
    brand = settings.YOUTUBE_BRAND_NAME.strip() or "Aksan"
    existing_tags = _unique(additional_tags or [])
    source_text = " ".join([title, *existing_tags])
    product_label, product_tags, hashtags = _product_context(source_text)
    lowered_source = source_text.casefold()

    if "костюм" in lowered_source and "трійка" in lowered_source and "велюр" in lowered_source:
        lead = f"Велюровий костюм-трійка {brand} для комфортних і стильних образів."
    elif "велюр" in lowered_source:
        lead = f"Велюровий {product_label} {brand}: м'яка фактура та продумані деталі."
    else:
        lead = f"{product_label.capitalize()} від {brand} для комфортних і стильних образів."

    description_lines = [
        lead,
        "У відео - фактура тканини, посадка та деталі виробу.",
        " ".join(hashtags),
    ]

    footer = settings.YOUTUBE_DESCRIPTION_FOOTER.strip()
    if footer:
        description_lines.extend(["", footer])

    tags = _within_tag_budget([
        brand,
        "Аксан",
        "жіночий одяг",
        "жіночий одяг Україна",
        "український жіночий одяг",
        "жіноча мода",
        "модний одяг",
        "новинки жіночого одягу",
        "магазин жіночого одягу",
        "виробник жіночого одягу",
        "Aksan clothing",
        *product_tags,
        "одяг Україна",
        *existing_tags,
        *_configured_extra_tags(),
    ])

    return YouTubeMetadata(
        title=title,
        description="\n".join(description_lines),
        tags=tags,
    )
