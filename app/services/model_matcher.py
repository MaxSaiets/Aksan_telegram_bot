"""
Model matching for numeric article codes (e.g. 25.2834 or 5.52.2554).

Strategy (priority order):
1. Extract numeric code from caption via regex  [0-9]+[.][0-9]+([.][0-9]+)*
2. Exact match against catalog's 'model' or 'sku' field
3. Fuzzy match on the extracted code (handles minor typos)
4. Fuzzy fallback on full cleaned caption text
5. Cross-reference matched SKU with Rozetka catalog
"""
import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Numeric code pattern: 25.2834  /  5.52.2554  /  1.44.3302 etc.
_CODE_PATTERN = re.compile(r"\b\d+\.\d+(?:\.\d+)*\b")

# Size category patterns — order matters: longer/multi-word forms first.
# Categories:
#   норма        → sizes 40, 42, 44
#   ботал        → sizes 46, 48, 50, 52, 54
#   супер ботал  → sizes 56, 58, 60
#   великий ботал → sizes 62, 64
#   мега ботал   → sizes 66, 68, 70
#
# Each tuple: (search_pattern, canonical_name)
_CATEGORIES = [
    ("суперботал",    "супер ботал"),
    ("супер ботал",   "супер ботал"),
    ("супербот",      "супер ботал"),
    ("великий ботал", "великий ботал"),
    ("мега ботал",    "мега ботал"),
    ("ботал",         "ботал"),
    ("бот",           "ботал"),        # abbreviation
    ("норма",         "норма"),
    ("норм",          "норма"),        # abbreviation
]

_SCORE_CUTOFF_CODE  = 85   # higher threshold when matching numeric codes
_SCORE_CUTOFF_TEXT  = 70   # lower threshold for text-based fallback


@dataclass
class MatchResult:
    model_name: str           # raw extracted code / cleaned caption
    product_name: str = ""    # human-readable name from SalesDrive (e.g. "Дриль 800Вт")
    sku: str | None = None
    salesdrive_id: str | None = None
    rozetka_id: str | None = None
    rozetka_url: str | None = None
    confidence: float = 0.0
    match_strategy: str = "none"   # "exact_code" / "fuzzy_code" / "fuzzy_text" / "none"
    matched: bool = field(init=False)

    def __post_init__(self):
        self.matched = self.sku is not None


# ─────────────────────────────────────────────────────────────────────────────

def extract_size_category(caption: str) -> str | None:
    """
    Extract size category suffix from caption.

    Examples:
        "20.8934_норма"        -> "норма"
        "20.8934 ботал"        -> "ботал"
        "25.2834_суперботал"   -> "супер ботал"
        "25.2834_супер ботал"  -> "супер ботал"
        "25.2834_бот"          -> "ботал"
        "25.2834_норм"         -> "норма"
        "25.2834_великий ботал"-> "великий ботал"
        "25.2834 дриль"        -> None
    """
    text = caption.lower()
    # Split by underscores and whitespace to get individual tokens/segments
    # This prevents false positives like "ботанічний" matching "бот"
    segments = re.split(r"[_\s]+", text)

    # First pass: try multi-word patterns by joining adjacent segments
    joined = " ".join(segments)
    for pattern, canonical in _CATEGORIES:
        if " " in pattern:
            # Multi-word pattern: search in joined text
            if pattern in joined:
                return canonical

    # Second pass: single-word patterns — must match a full segment
    for pattern, canonical in _CATEGORIES:
        if " " not in pattern:
            for seg in segments:
                if seg == pattern:
                    return canonical

    return None


def extract_numeric_codes(caption: str) -> list[str]:
    """
    Extract all numeric codes from a caption string.

    Examples:
        "Відео про дриль 25.2834 класно!"  ->  ["25.2834"]
        "5.52.2554 та ще 12.4567"          ->  ["5.52.2554", "12.4567"]
        "Samsung Galaxy S24"               ->  []
    """
    return _CODE_PATTERN.findall(caption)


def clean_caption(caption: str) -> str:
    """Remove hashtags, prices, extra whitespace from caption."""
    cleaned = re.sub(r"#\S+", "", caption)
    cleaned = re.sub(r"\d+\s*(грн|uah|usd|\$)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned or caption.strip()


def _exact_lookup(code: str, items: list[dict]) -> dict | None:
    """Find catalog item where model OR sku exactly equals code."""
    for item in items:
        if item.get("model") == code or item.get("sku") == code:
            return item
    return None


def _fuzzy_lookup(
    query: str,
    items: list[dict],
    key: str,
    score_cutoff: int,
) -> tuple[dict | None, float]:
    """Fuzzy search `query` in items[key]. Returns (item, 0.0–1.0)."""
    if not items:
        return None, 0.0
    choices = [item[key] for item in items]
    result = process.extractOne(
        query, choices, scorer=fuzz.WRatio, score_cutoff=score_cutoff
    )
    if result is None:
        return None, 0.0
    _text, score, idx = result
    return items[idx], score / 100.0


def _rozetka_by_sku(sku: str, rz_catalog: list[dict]) -> dict | None:
    """Cross-reference: find Rozetka item with matching sku."""
    for item in rz_catalog:
        if item.get("sku") == sku:
            return item
    # fallback: fuzzy on model field
    rz_item, _ = _fuzzy_lookup(sku, rz_catalog, "model", _SCORE_CUTOFF_CODE)
    return rz_item


# ─────────────────────────────────────────────────────────────────────────────

def match_model(
    caption: str,
    sd_catalog: list[dict],
    rozetka_catalog: list[dict],
) -> MatchResult:
    """
    Main matching function.

    Args:
        caption:           Raw text caption (e.g. "Товар 25.2834 опис").
        sd_catalog:        SalesDrive products — each must have 'model' and 'sku'.
        rozetka_catalog:   Rozetka products   — each must have 'model', 'sku', 'url'.

    Returns:
        MatchResult — always returned, check .matched to know if found.
    """
    codes = extract_numeric_codes(caption)
    size_category = extract_size_category(caption)
    logger.info(
        "Caption: '%s' | Extracted codes: %s | Category: %s",
        caption[:60], codes, size_category,
    )

    sd_item: dict | None = None
    strategy = "none"
    confidence = 0.0
    matched_code = caption  # what we'll store as model_name

    # ── Strategy 1: exact match on extracted numeric code(s) ─────────────────
    for code in codes:
        sd_item = _exact_lookup(code, sd_catalog)
        if sd_item:
            matched_code = code
            strategy = "exact_code"
            confidence = 1.0
            logger.info(
                "Exact match: code='%s' => sku=%s name='%s'",
                code, sd_item["sku"], sd_item.get("name", "")
            )
            break

    # ── Strategy 2: fuzzy match on extracted code(s) ─────────────────────────
    if sd_item is None and codes:
        for code in codes:
            item, score = _fuzzy_lookup(code, sd_catalog, "model", _SCORE_CUTOFF_CODE)
            if item is None:
                item, score = _fuzzy_lookup(code, sd_catalog, "sku", _SCORE_CUTOFF_CODE)
            if item:
                sd_item = item
                matched_code = code
                strategy = "fuzzy_code"
                confidence = score
                logger.info(
                    "Fuzzy code match: code='%s' => sku=%s (%.0f%%)",
                    code, item["sku"], score * 100
                )
                break

    # ── Strategy 3: fuzzy match on full cleaned caption (text fallback) ───────
    if sd_item is None:
        cleaned = clean_caption(caption)
        item, score = _fuzzy_lookup(cleaned, sd_catalog, "model", _SCORE_CUTOFF_TEXT)
        if item is None:
            item, score = _fuzzy_lookup(cleaned, sd_catalog, "name", _SCORE_CUTOFF_TEXT)
        if item:
            sd_item = item
            matched_code = cleaned
            strategy = "fuzzy_text"
            confidence = score
            logger.info(
                "Fuzzy text match: query='%s' => sku=%s (%.0f%%)",
                cleaned[:40], item["sku"], score * 100
            )

    if sd_item is None:
        logger.warning("No match found for caption: '%s'", caption[:60])
        return MatchResult(model_name=clean_caption(caption) or caption)

    # ── Build final SKU with size category suffix ─────────────────────────────
    base_sku = sd_item["sku"]
    final_sku = f"{base_sku}_{size_category}" if size_category else base_sku
    if size_category:
        logger.info("SKU with category: %s", final_sku)

    # ── Cross-reference with Rozetka by base SKU ──────────────────────────────
    rz_item = _rozetka_by_sku(base_sku, rozetka_catalog)
    if rz_item:
        logger.info("Rozetka match: sku=%s => %s", base_sku, rz_item.get("url", ""))

    return MatchResult(
        model_name=matched_code,
        product_name=sd_item.get("name", ""),
        sku=final_sku,
        salesdrive_id=sd_item.get("id"),
        rozetka_id=rz_item.get("id") if rz_item else None,
        rozetka_url=rz_item.get("url") if rz_item else None,
        confidence=confidence,
        match_strategy=strategy,
    )
