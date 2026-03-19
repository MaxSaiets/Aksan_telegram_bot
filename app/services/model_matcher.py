"""Exact model matching helpers."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.sku_parser import extract_category, extract_model_code
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MatchResult:
    model_name: str
    product_name: str = ""
    sku: str | None = None
    salesdrive_id: str | None = None
    rozetka_id: str | None = None
    rozetka_url: str | None = None
    confidence: float = 0.0
    match_strategy: str = "none"
    matched: bool = field(init=False)

    def __post_init__(self):
        self.matched = self.sku is not None


def extract_size_category(caption: str) -> str | None:
    return extract_category(caption)


def extract_numeric_codes(caption: str) -> list[str]:
    code = extract_model_code(caption)
    return [code] if code else []


def clean_caption(caption: str) -> str:
    return (caption or "").strip()


def _exact_lookup(code: str, items: list[dict]) -> dict | None:
    for item in items:
        if item.get("model") == code or item.get("sku") == code:
            return item
    return None


def _rozetka_by_sku(sku: str, rz_catalog: list[dict]) -> dict | None:
    for item in rz_catalog:
        if item.get("sku") == sku or item.get("model") == sku:
            return item
    return None


def match_model(caption: str, sd_catalog: list[dict], rozetka_catalog: list[dict]) -> MatchResult:
    """
    Match by exact numeric code only.

    No fuzzy matching is used.
    """
    code = extract_model_code(caption or "")
    category = extract_category(caption or "")
    logger.info("Caption='%s' | code=%s | category=%s", caption[:60], code, category)

    if not code:
        return MatchResult(model_name=clean_caption(caption))

    sd_item = _exact_lookup(code, sd_catalog)
    if not sd_item:
        logger.warning("No exact SalesDrive match for code=%s", code)
        return MatchResult(model_name=code)

    rz_item = _rozetka_by_sku(code, rozetka_catalog)
    final_sku = f"{code}_{category}" if category else code
    return MatchResult(
        model_name=code,
        product_name=sd_item.get("name", ""),
        sku=final_sku,
        salesdrive_id=sd_item.get("id"),
        rozetka_id=rz_item.get("id") if rz_item else None,
        rozetka_url=rz_item.get("url") if rz_item else None,
        confidence=1.0,
        match_strategy="exact_code",
    )
