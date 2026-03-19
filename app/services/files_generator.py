"""
Generate Excel files for Rozetka video import and website video mapping.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from config import settings
from app.services.sku_parser import (
    allowed_sizes_for_category,
    extract_variant_size,
    variant_matches_category,
)
from app.services.youtube_catalog import fetch_channel_videos
from app.utils.logger import get_logger

logger = get_logger(__name__)

_EXPORTED_ROZETKA_PATH = Path("tmp/exported_rozetka.json")
_EXPORTED_SITE_PATH = Path("tmp/exported_site.json")


def _load_exported(path: Path) -> set[str]:
    if path.exists():
        try:
            return set(json.loads(path.read_text(encoding="utf-8")).get("ids", []))
        except Exception:
            pass
    return set()


def _save_exported(path: Path, new_ids: set[str]) -> None:
    existing = _load_exported(path)
    merged = existing | {str(item) for item in new_ids}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"ids": sorted(merged)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _remove_from_exported(path: Path, ids_to_remove: set[str]) -> None:
    existing = _load_exported(path)
    cleaned = existing - {str(item) for item in ids_to_remove}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"ids": sorted(cleaned)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def remove_from_exported(sku: str, model_code: str) -> None:
    base_model = model_code.split("_")[0] if "_" in model_code else model_code
    _remove_from_exported(_EXPORTED_SITE_PATH, {base_model, sku})

    try:
        for variant in _fetch_all_rozetka_variants():
            if variant.get("model") == base_model:
                _remove_from_exported(_EXPORTED_ROZETKA_PATH, {str(variant["rz_item_id"])})
                _remove_from_exported(_EXPORTED_SITE_PATH, {variant["article"]})
    except Exception as exc:
        logger.warning("Could not clean exported sets for model %s: %s", base_model, exc)


def _fetch_all_rozetka_variants() -> list[dict]:
    if settings.USE_MOCKS:
        return [
            {
                "rz_item_id": 100001,
                "article": "26.2873_red_40(S)",
                "model": "26.2873",
                "name_ua": "Костюм 40 червоний",
                "url": "https://rozetka.com.ua/100001/p100001",
            },
            {
                "rz_item_id": 100002,
                "article": "26.2873_red_42(M)",
                "model": "26.2873",
                "name_ua": "Костюм 42 червоний",
                "url": "https://rozetka.com.ua/100002/p100002",
            },
            {
                "rz_item_id": 100003,
                "article": "26.2873_black_44(L)",
                "model": "26.2873",
                "name_ua": "Костюм 44 чорний",
                "url": "https://rozetka.com.ua/100003/p100003",
            },
            {
                "rz_item_id": 100004,
                "article": "26.2861_black_50(XL)",
                "model": "26.2861",
                "name_ua": "Костюм 50 чорний",
                "url": "https://rozetka.com.ua/100004/p100004",
            },
            {
                "rz_item_id": 100005,
                "article": "26.2861_beige_52(2XL)",
                "model": "26.2861",
                "name_ua": "Костюм 52 бежевий",
                "url": "https://rozetka.com.ua/100005/p100005",
            },
            {
                "rz_item_id": 100006,
                "article": "26.2630_grey_56(3XL)",
                "model": "26.2630",
                "name_ua": "Костюм 56 сірий",
                "url": "https://rozetka.com.ua/100006/p100006",
            },
        ]

    from app.services.rozetka import _ROZETKA_BASE  # noqa: PLC2701
    import httpx

    headers = {"Authorization": f"Bearer {settings.ROZETKA_API_KEY}"}
    all_items: list[dict] = []
    page = 1
    per_page = 100

    with httpx.Client(headers=headers, timeout=60, verify=False) as client:
        while True:
            resp = client.get(
                f"{_ROZETKA_BASE}/goods/all",
                params={"page": page, "per_page": per_page},
            )
            resp.raise_for_status()
            content = resp.json().get("content", {})
            items = content.get("items", [])
            if not items:
                break

            for item in items:
                article = item.get("article", "")
                model = article.split("_")[0].strip() if article else ""
                all_items.append({
                    "rz_item_id": item["rz_item_id"],
                    "article": article,
                    "model": model,
                    "name_ua": item.get("name_ua") or item.get("name", ""),
                    "url": item.get("url", ""),
                })

            if page * per_page >= content.get("count", 0):
                break
            page += 1

    logger.info("Rozetka: fetched %d variants total", len(all_items))
    return all_items


def _autofit(ws, df: pd.DataFrame) -> None:
    for ci, col in enumerate(df.columns, 1):
        width = max(
            len(str(col)),
            df[col].astype(str).map(len).max() if not df.empty else 0,
        )
        ws.column_dimensions[ws.cell(1, ci).column_letter].width = min(width + 4, 70)


def _latest_video_map() -> dict[tuple[str, str], dict]:
    videos = sorted(fetch_channel_videos(), key=lambda item: item["published_at"])
    latest: dict[tuple[str, str], dict] = {}
    for video in videos:
        model = video.get("model")
        category = video.get("category")
        if model and category:
            latest[(model, category)] = video
    return latest


def _variant_groups_by_model(variants: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for variant in variants:
        grouped[variant["model"]].append(variant)
    return grouped


def generate_rozetka_file(on_progress: Callable[[str], None] | None = None) -> tuple[Path, int]:
    _progress = on_progress or (lambda msg: None)
    _progress("[1/4] Завантажую відео з YouTube...")
    video_map = _latest_video_map()
    _progress(f"[1/4] Знайдено {len(video_map)} унікальних model/category відео")

    _progress("[2/4] Завантажую варіанти з Розетки...")
    variants = _fetch_all_rozetka_variants()
    grouped = _variant_groups_by_model(variants)
    _progress(f"[2/4] Розетка: {len(variants)} варіантів")

    already = _load_exported(_EXPORTED_ROZETKA_PATH)
    rows: list[dict] = []
    new_ids: set[str] = set()

    _progress("[3/4] Підбираю варіанти за точним SKU і категорією...")
    for (model, category), video in video_map.items():
        model_variants = grouped.get(model, [])
        available_sizes = {
            size for size in (extract_variant_size(item["article"]) for item in model_variants)
            if size is not None
        }
        allowed_sizes = allowed_sizes_for_category(category, available_sizes)
        if not allowed_sizes:
            continue

        for variant in model_variants:
            rz_id = str(variant["rz_item_id"])
            if rz_id in already:
                continue
            if not variant_matches_category(variant["article"], category, available_sizes):
                continue

            rows.append({
                "Код товару на ROZETKA": variant["rz_item_id"],
                "Посилання на товар на сайті ROZETKA": variant["url"],
                "ID товару у вашому прайс-листі": variant["article"],
                "Назва товару": variant["name_ua"],
                "Посилання на відео": video["url"],
            })
            new_ids.add(rz_id)

    _progress(f"[3/4] Нових рядків: {len(rows)}")

    _progress("[4/4] Записую Excel...")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = settings.temp_dir / f"rozetka_videos_{ts}.xlsx"
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(str(out), engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Добавление видеообзора")
        _autofit(writer.sheets["Добавление видеообзора"], df)

    _save_exported(_EXPORTED_ROZETKA_PATH, new_ids)
    logger.info("Rozetka file: %d new rows -> %s", len(rows), out)
    return out, len(rows)


def generate_site_file(on_progress: Callable[[str], None] | None = None) -> tuple[Path, int]:
    _progress = on_progress or (lambda msg: None)
    _progress("[1/4] Завантажую відео з YouTube...")
    video_map = _latest_video_map()

    _progress("[2/4] Завантажую варіанти з Розетки...")
    variants = _fetch_all_rozetka_variants()
    grouped = _variant_groups_by_model(variants)

    already = _load_exported(_EXPORTED_SITE_PATH)
    rows: list[dict] = []
    new_articles: set[str] = set()

    _progress("[3/4] Формую рядки для всіх кольорів і різновидів...")
    for (model, category), video in video_map.items():
        model_variants = grouped.get(model, [])
        available_sizes = {
            size for size in (extract_variant_size(item["article"]) for item in model_variants)
            if size is not None
        }
        if not available_sizes:
            continue

        for variant in model_variants:
            article = variant["article"]
            if article in already:
                continue
            if not variant_matches_category(article, category, available_sizes):
                continue

            rows.append({
                "SKU": article,
                "Посилання на відео": video["url"],
            })
            new_articles.add(article)

    _progress(f"[3/4] Нових SKU: {len(rows)}")

    _progress("[4/4] Записую Excel...")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = settings.temp_dir / f"site_videos_{ts}.xlsx"
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(str(out), engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Відео для сайту")
        _autofit(writer.sheets["Відео для сайту"], df)

    _save_exported(_EXPORTED_SITE_PATH, new_articles)
    logger.info("Site file: %d new rows -> %s", len(rows), out)
    return out, len(rows)
