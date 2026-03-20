"""
Fetch product catalog from SalesDrive CRM via public YML export.
- USE_MOCKS=true  -> returns a hardcoded mock catalog/feed
- USE_MOCKS=false -> downloads and parses YML from SALESDRIVE_YML_URL

YML format: standard Yandex/Prom YML feed.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx

from app.utils.logger import get_logger
from config import settings

logger = get_logger(__name__)

_MOCK_CATALOG = [
    {"id": "SD-001", "sku": "25.2834", "model": "25.2834", "name": "Дриль електричний 800Вт"},
    {"id": "SD-002", "sku": "5.52.2554", "model": "5.52.2554", "name": "Перфоратор SDS+ 1200Вт"},
    {"id": "SD-003", "sku": "12.4567", "model": "12.4567", "name": "Болгарка кутова 125мм"},
]

_MOCK_FEED_VARIANTS = [
    {"article": "26.2873_red_40(S)", "model": "26.2873", "name_ua": "Костюм 40 червоний"},
    {"article": "26.2873_red_42(M)", "model": "26.2873", "name_ua": "Костюм 42 червоний"},
    {"article": "26.2873_black_44(L)", "model": "26.2873", "name_ua": "Костюм 44 чорний"},
    {"article": "26.2861_black_50(XL)", "model": "26.2861", "name_ua": "Костюм 50 чорний"},
    {"article": "26.2861_beige_52(2XL)", "model": "26.2861", "name_ua": "Костюм 52 бежевий"},
    {"article": "26.2630_grey_56(3XL)", "model": "26.2630", "name_ua": "Костюм 56 сірий"},
]


def _extract_model(article: str) -> str:
    return article.split("_")[0].strip() if article else ""


def _load_yml_root() -> ET.Element:
    resp = httpx.get(settings.SALESDRIVE_YML_URL, timeout=60, follow_redirects=True)
    resp.raise_for_status()
    return ET.fromstring(resp.content)


def _real_fetch_catalog() -> list[dict]:
    root = _load_yml_root()
    offers = root.findall(".//offer")

    seen: dict[str, dict] = {}
    for offer in offers:
        group_id = offer.get("group_id") or offer.get("id", "")
        if not group_id or group_id in seen:
            continue

        article = offer.findtext("article") or offer.findtext("vendorCode") or offer.get("id", "")
        model = _extract_model(article)
        name = offer.findtext("name_ua") or offer.findtext("name") or ""
        seen[group_id] = {
            "id": group_id,
            "sku": model,
            "model": model,
            "name": name,
        }

    result = list(seen.values())
    logger.info("SalesDrive YML: fetched %d product groups", len(result))
    return result


def _real_fetch_feed_variants() -> list[dict]:
    root = _load_yml_root()
    offers = root.findall(".//offer")

    seen: dict[str, dict] = {}
    for offer in offers:
        article = offer.findtext("article") or offer.findtext("vendorCode") or offer.get("id", "")
        if not article or article in seen:
            continue

        model = _extract_model(article)
        name = offer.findtext("name_ua") or offer.findtext("name") or ""
        seen[article] = {
            "article": article,
            "model": model,
            "name_ua": name,
        }

    result = list(seen.values())
    logger.info("SalesDrive YML: fetched %d offer variants", len(result))
    return result


def fetch_catalog() -> list[dict]:
    if settings.USE_MOCKS:
        logger.info("[MOCK SalesDrive] Returning %d mock products", len(_MOCK_CATALOG))
        return _MOCK_CATALOG

    if not settings.SALESDRIVE_YML_URL:
        logger.warning("SALESDRIVE_YML_URL not set — returning empty catalog")
        return []

    try:
        from app.services.catalog_cache import get_cached
        return get_cached("catalog:salesdrive", _real_fetch_catalog)
    except Exception as exc:
        logger.error("SalesDrive YML fetch failed: %s — returning empty catalog", exc)
        return []


def fetch_feed_variants() -> list[dict]:
    if settings.USE_MOCKS:
        logger.info("[MOCK SalesDrive] Returning %d mock offer variants", len(_MOCK_FEED_VARIANTS))
        return list(_MOCK_FEED_VARIANTS)

    if not settings.SALESDRIVE_YML_URL:
        logger.warning("SALESDRIVE_YML_URL not set — returning empty offer feed")
        return []

    try:
        from app.services.catalog_cache import get_cached
        return get_cached("catalog:salesdrive:offers", _real_fetch_feed_variants)
    except Exception as exc:
        logger.error("SalesDrive offer feed fetch failed: %s — returning empty feed", exc)
        return []