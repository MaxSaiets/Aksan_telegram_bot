"""
Catalog caching layer.

- USE_MOCKS=true  → in-memory dict (no Redis needed, no TTL — dev mode)
- USE_MOCKS=false → Redis with configurable TTL (default 30 min)

Graceful degradation: if Redis is unavailable, falls back to direct fetch.
"""
import json

from config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

_CATALOG_TTL = 1800       # 30 minutes
_memory_cache: dict = {}  # used in mock mode only


def get_cached(key: str, fetch_fn: callable, ttl: int = _CATALOG_TTL) -> list[dict]:
    """
    Return data for `key` from cache.
    On cache miss, call `fetch_fn()`, store result, and return it.
    """
    if settings.USE_MOCKS:
        if key not in _memory_cache:
            _memory_cache[key] = fetch_fn()
            logger.debug("Memory cache SET: %s (%d items)", key, len(_memory_cache[key]))
        else:
            logger.debug("Memory cache HIT: %s", key)
        return _memory_cache[key]

    # ── Real mode: Redis ──────────────────────────────────────────────────────
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=2)

        raw = r.get(key)
        if raw:
            logger.debug("Redis cache HIT: %s", key)
            return json.loads(raw)

        data = fetch_fn()
        r.setex(key, ttl, json.dumps(data, ensure_ascii=False))
        logger.info("Redis cache SET: %s (%d items, TTL=%ds)", key, len(data), ttl)
        return data

    except Exception as exc:
        logger.warning("Cache unavailable (%s), fetching directly", exc)
        return fetch_fn()


def invalidate(key: str) -> None:
    """
    Manually invalidate a cache entry.
    Call this after a catalog update in SalesDrive/Rozetka.
    """
    _memory_cache.pop(key, None)

    if settings.USE_MOCKS:
        return

    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=2)
        r.delete(key)
        logger.info("Cache invalidated: %s", key)
    except Exception as exc:
        logger.warning("Could not invalidate cache key '%s': %s", key, exc)


def invalidate_all() -> None:
    """Invalidate all catalog caches (e.g. after bulk product import)."""
    _memory_cache.clear()
    invalidate("catalog:salesdrive")
    invalidate("catalog:rozetka")
