"""Build natural, search-friendly YouTube metadata without changing titles."""
from __future__ import annotations

from dataclasses import dataclass

from config import settings
from app.services.youtube_copywriter import generate_youtube_description


_YOUTUBE_TAG_LIMIT = 500
_BASE_DISCOVERY_TAGS = [
    "Aksan",
    "Аксан",
    "Aksan clothing",
    "Aksan Україна",
    "Aksan жіночий одяг",
    "жіночий одяг",
    "жіночий одяг Україна",
    "український жіночий одяг",
    "український бренд одягу",
    "виробник жіночого одягу",
    "магазин жіночого одягу",
    "інтернет магазин жіночого одягу",
    "модний жіночий одяг",
    "стильний жіночий одяг",
    "новинки жіночого одягу",
    "одяг для жінок",
    "жіноча мода Україна",
    "базовий гардероб жіночий",
    "жіночі образи",
    "одяг Україна",
    "жіночий одяг від виробника",
    "брендовий жіночий одяг",
    "сучасна жіноча мода",
    "українська мода",
    "гардероб для жінок",
    "жіночий одяг онлайн",
    "купити жіночий одяг",
    "українські бренди одягу",
]
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
    "лонгслів": ("жіночий лонгслів", ["жіночий лонгслів", "лонгслів жіночий"]),
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
    if "вельвет" in lowered:
        product_tags.extend(["вельветовий костюм", "костюм з вельвету", "вельвет"])
        hashtags.append("#вельветовийкостюм")
    if "байка" in lowered and "штани" in lowered:
        product_tags.extend(["жіночі штани на байці", "штани на байці", "байкові штани"])
        hashtags.append("#штанинаяці")
    if "віскоза" in lowered and "лонгслів" in lowered:
        product_tags.extend(["лонгслів з віскози", "віскозний лонгслів", "віскоза"])
        hashtags.append("#віскоза")

    hashtags.extend(["#українськийодяг", "#жіночамода", "#новинкиодягу"])
    return label, _unique(product_tags), _unique(hashtags)[:5]


def tag_character_count(tags: list[str]) -> int:
    """Match YouTube's 500-character rule, including commas and space quotes."""
    return sum(len(tag) + (2 if " " in tag else 0) for tag in tags) + max(len(tags) - 1, 0)


def _within_tag_budget(tags: list[str]) -> list[str]:
    budget = min(max(settings.YOUTUBE_TAG_TARGET_CHARACTERS, 1), _YOUTUBE_TAG_LIMIT)
    result: list[str] = []
    for tag in _unique(tags):
        if tag_character_count([*result, tag]) <= budget:
            result.append(tag)
    return result


def build_youtube_metadata(caption: str, additional_tags: list[str] | None = None) -> YouTubeMetadata:
    """Create description and tags while keeping the supplied title unchanged."""
    title = (caption or "").strip()
    brand = settings.YOUTUBE_BRAND_NAME.strip() or "Aksan"
    existing_tags = _unique(additional_tags or [])
    source_text = " ".join([title, *existing_tags])
    _, product_tags, hashtags = _product_context(source_text)

    description = generate_youtube_description(title, brand)

    description_lines = [
        description,
        " ".join(hashtags),
    ]

    footer = settings.YOUTUBE_DESCRIPTION_FOOTER.strip()
    if footer:
        description_lines.extend(["", footer])

    tags = _within_tag_budget([
        brand,
        *product_tags,
        *existing_tags,
        *_configured_extra_tags(),
        *_BASE_DISCOVERY_TAGS,
    ])

    return YouTubeMetadata(
        title=title,
        description="\n".join(description_lines),
        tags=tags,
    )
