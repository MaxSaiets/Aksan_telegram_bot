"""
Fetch product catalog from SalesDrive CRM via public YML export.
- USE_MOCKS=true  → returns a hardcoded mock catalog
- USE_MOCKS=false → downloads and parses YML from SALESDRIVE_YML_URL

YML format: standard Yandex/Prom YML feed.
  <offer id="26.2873_red_46(L)" group_id="117440">
    <article>26.2873_red_46(L)</article>
    <vendorCode>26.2873_red_46(L)</vendorCode>
    <name_ua>Жіночий спортивний костюм ...</name_ua>
    ...
  </offer>

Result format per item: {"id", "sku", "model", "name"}
  id    = group_id attribute (one record per product group, not per variant)
  sku   = model code = part of article before first "_"  (e.g. "26.2873")
  model = same as sku
  name  = name_ua (or name if name_ua absent)
"""
import xml.etree.ElementTree as ET

import httpx

from config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ─── Mock catalog ─────────────────────────────────────────────────────────────

_MOCK_CATALOG = [
    {"id": "SD-001", "sku": "25.2834",   "model": "25.2834",   "name": "Дриль електричний 800Вт"},
    {"id": "SD-002", "sku": "5.52.2554", "model": "5.52.2554", "name": "Перфоратор SDS+ 1200Вт"},
    {"id": "SD-003", "sku": "12.4567",   "model": "12.4567",   "name": "Болгарка кутова 125мм"},
]


def _extract_model(article: str) -> str:
    """Extract numeric model code from article string.

    "26.2873_red_46(L)" → "26.2873"
    "26.2873"           → "26.2873"
    """
    return article.split("_")[0].strip() if article else ""


def _real_fetch() -> list[dict]:
    """Download YML export and return one record per product group."""
    resp = httpx.get(settings.SALESDRIVE_YML_URL, timeout=60, follow_redirects=True)
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    offers = root.findall(".//offer")

    seen: dict[str, dict] = {}  # group_id → product dict

    for offer in offers:
        group_id = offer.get("group_id") or offer.get("id", "")
        if not group_id or group_id in seen:
            continue

        article = (
            offer.findtext("article")
            or offer.findtext("vendorCode")
            or offer.get("id", "")
        )
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


def fetch_catalog() -> list[dict]:
    """
    Return the full product catalog from SalesDrive.
    Mock mode returns hardcoded data; real mode parses YML (cached 30 min in Redis).
    Falls back to empty list if URL is not configured or request fails.
    """
    if settings.USE_MOCKS:
        logger.info("[MOCK SalesDrive] Returning %d mock products", len(_MOCK_CATALOG))
        return _MOCK_CATALOG

    if not settings.SALESDRIVE_YML_URL:
        logger.warning("SALESDRIVE_YML_URL not set — returning empty catalog")
        return []

    try:
        from app.services.catalog_cache import get_cached
        return get_cached("catalog:salesdrive", _real_fetch)
    except Exception as exc:
        logger.error("SalesDrive YML fetch failed: %s — returning empty catalog", exc)
        return []
