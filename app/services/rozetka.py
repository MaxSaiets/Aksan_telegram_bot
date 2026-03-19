"""
Fetch product data from Rozetka marketplace.
- USE_MOCKS=true  → returns hardcoded mock data
- USE_MOCKS=false → calls Rozetka Seller API
"""
import httpx

from config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

_ROZETKA_BASE = "https://api-seller.rozetka.com.ua"

# ─── Mock Rozetka items ───────────────────────────────────────────────────────
_MOCK_ROZETKA = [
    # Артикули мають збігатися з SalesDrive для коректного cross-reference
    {"id": "RZ-10001", "model": "25.2834",   "sku": "25.2834",   "url": "https://rozetka.com.ua/ua/drill-800w/p100001/"},
    {"id": "RZ-10002", "model": "5.52.2554", "sku": "5.52.2554", "url": "https://rozetka.com.ua/ua/perforator-1200w/p100002/"},
    {"id": "RZ-10003", "model": "12.4567",   "sku": "12.4567",   "url": "https://rozetka.com.ua/ua/bolharka-125/p100003/"},
    {"id": "RZ-10004", "model": "3.21.1089", "sku": "3.21.1089", "url": "https://rozetka.com.ua/ua/shurupovert-18v/p100004/"},
    {"id": "RZ-10005", "model": "8.9901",    "sku": "8.9901",    "url": "https://rozetka.com.ua/ua/lobzyk-750w/p100005/"},
    {"id": "RZ-10006", "model": "1.44.3302", "sku": "1.44.3302", "url": "https://rozetka.com.ua/ua/pylosos-30l/p100006/"},
    {"id": "RZ-10007", "model": "25.2835",   "sku": "25.2835",   "url": "https://rozetka.com.ua/ua/drill-1000w/p100007/"},
    {"id": "RZ-10008", "model": "7.6678",    "sku": "7.6678",    "url": "https://rozetka.com.ua/ua/riven-3d/p100008/"},
    {"id": "RZ-10009", "model": "2.18.4421", "sku": "2.18.4421", "url": "https://rozetka.com.ua/ua/kompresor-50l/p100009/"},
    {"id": "RZ-10010", "model": "11.3345",   "sku": "11.3345",   "url": "https://rozetka.com.ua/ua/frezer-1200w/p100010/"},
]


def _real_fetch() -> list[dict]:
    """Fetch live listings from Rozetka Seller API using API key.

    Response structure:
      content.count       — total items
      content.items[]     — list of goods (multiple variants per product group)
        rz_group_id       — product group ID (dedup key)
        article           — "26.2873_red_42(S)" → model = "26.2873"
        url               — "https://rozetka.com.ua/582056146/p582056146"
        name_ua           — Ukrainian product name

    We deduplicate by rz_group_id (one URL per product group).
    """
    headers = {"Authorization": f"Bearer {settings.ROZETKA_API_KEY}"}
    seen: dict[str, dict] = {}  # rz_group_id → item dict
    page = 1
    per_page = 100

    with httpx.Client(headers=headers, timeout=30, verify=False) as client:
        while True:
            resp = client.get(
                f"{_ROZETKA_BASE}/goods/all",
                params={"page": page, "per_page": per_page},
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("content", {})
            items = content.get("items", [])
            if not items:
                break

            for item in items:
                group_id = str(item.get("rz_group_id") or item.get("rz_item_id", ""))
                if not group_id or group_id in seen:
                    continue
                article = item.get("article", "")
                model = article.split("_")[0].strip() if article else ""
                seen[group_id] = {
                    "id": group_id,
                    "model": model,
                    "sku": model,
                    "url": item.get("url", ""),
                }

            total = content.get("count", 0)
            if page * per_page >= total:
                break
            page += 1

    result = list(seen.values())
    logger.info("Rozetka: fetched %d product groups (from API)", len(result))
    return result


def fetch_catalog() -> list[dict]:
    """
    Return all Rozetka listings for your seller account.
    Mock mode returns hardcoded data; real mode uses Redis cache (TTL 30 min).
    Falls back to empty list if the API is unavailable or not configured.
    Each item: {"id", "model", "sku", "url"}
    """
    if settings.USE_MOCKS:
        logger.info("[MOCK Rozetka] Returning %d mock products", len(_MOCK_ROZETKA))
        return _MOCK_ROZETKA

    if not settings.ROZETKA_API_KEY or "MOCK" in settings.ROZETKA_API_KEY.upper():
        logger.warning("ROZETKA_API_KEY not configured — returning empty catalog")
        return []

    try:
        from app.services.catalog_cache import get_cached
        return get_cached("catalog:rozetka", _real_fetch)
    except Exception as exc:
        logger.error("Rozetka fetch failed: %s — returning empty catalog", exc)
        return []
