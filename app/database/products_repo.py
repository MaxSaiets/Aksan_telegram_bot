"""CRUD operations for the `products` table."""
import uuid
from datetime import datetime, timezone

from app.database.client import db_client
from app.utils.logger import get_logger

logger = get_logger(__name__)


def create_product(
    video_id: str,
    model_name: str,
    sku: str | None,
    youtube_url: str | None,
    product_name: str = "",
    salesdrive_product_id: str | None = None,
    rozetka_product_id: str | None = None,
    rozetka_url: str | None = None,
    match_confidence: float = 0.0,
) -> dict:
    data = {
        "id": str(uuid.uuid4()),
        "video_id": video_id,
        "model_name": model_name,
        "product_name": product_name,
        "sku": sku,
        "salesdrive_product_id": salesdrive_product_id,
        "rozetka_product_id": rozetka_product_id,
        "rozetka_url": rozetka_url,
        "youtube_url": youtube_url,
        "match_confidence": match_confidence,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    row = db_client.insert("products", data)
    logger.info(
        "Saved product: model=%s sku=%s name='%s' confidence=%.2f",
        model_name, sku, product_name, match_confidence,
    )
    return row


def get_all_products() -> list[dict]:
    return db_client.select("products")


def get_products_for_video(video_id: str) -> list[dict]:
    return db_client.select("products", {"video_id": video_id})


def find_by_sku(sku: str) -> dict | None:
    """Find existing product record by SKU."""
    all_products = db_client.select("products", {"sku": sku})
    return all_products[0] if all_products else None


def update_product(product_id: str, data: dict) -> dict | None:
    """Update an existing product record."""
    result = db_client.update("products", {"id": product_id}, data)
    logger.info("Updated product id=%s with %s", product_id, list(data.keys()))
    return result


def upsert_product(
    video_id: str,
    model_name: str,
    sku: str | None,
    youtube_url: str | None,
    product_name: str = "",
    salesdrive_product_id: str | None = None,
    rozetka_product_id: str | None = None,
    rozetka_url: str | None = None,
    match_confidence: float = 0.0,
) -> tuple[dict, bool]:
    """
    Create or update a product record.

    If a product with the same SKU already exists, update it with the new video.
    Returns (product_dict, is_update).
    """
    if sku:
        existing = find_by_sku(sku)
        if existing:
            updated = update_product(existing["id"], {
                "video_id": video_id,
                "model_name": model_name,
                "product_name": product_name,
                "youtube_url": youtube_url,
                "salesdrive_product_id": salesdrive_product_id,
                "rozetka_product_id": rozetka_product_id,
                "rozetka_url": rozetka_url,
                "match_confidence": match_confidence,
            })
            logger.info(
                "Updated product for sku=%s with new video_id=%s youtube=%s",
                sku, video_id, youtube_url,
            )
            return updated, True

    row = create_product(
        video_id=video_id,
        model_name=model_name,
        sku=sku,
        youtube_url=youtube_url,
        product_name=product_name,
        salesdrive_product_id=salesdrive_product_id,
        rozetka_product_id=rozetka_product_id,
        rozetka_url=rozetka_url,
        match_confidence=match_confidence,
    )
    return row, False


def get_all_with_sku() -> list[dict]:
    """Return all products that have a matched SKU."""
    all_products = get_all_products()
    return [p for p in all_products if p.get("sku")]
