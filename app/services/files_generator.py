"""
Generate Excel files for Rozetka video import and website video mapping.

Rozetka file — sheet "Добавление видеообзора", 5 columns:
  Код товару на ROZETKA | Посилання на товар на сайті ROZETKA |
  ID товару у вашому прайс-листі | Назва товару | Посилання на відео

  One row per Rozetka VARIANT (all colors/sizes of a model get the same video URL).

Site file — 2 columns:
  SKU | Посилання на відео
  One row per model.

"New only" logic:
  Exported rz_item_ids  → tracked in tmp/exported_rozetka.json
  Exported model SKUs   → tracked in tmp/exported_site.json
  Each generate call updates the respective file so next call skips already-sent items.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Callable

import httpx
import pandas as pd

from config import settings
from app.services.youtube_catalog import fetch_channel_videos
from app.utils.logger import get_logger

logger = get_logger(__name__)

_EXPORTED_ROZETKA_PATH = Path("tmp/exported_rozetka.json")
_EXPORTED_SITE_PATH    = Path("tmp/exported_site.json")


# ── Exported-set helpers ──────────────────────────────────────────────────────

def _load_exported(path: Path) -> set[str]:
    if path.exists():
        try:
            return set(json.loads(path.read_text(encoding="utf-8")).get("ids", []))
        except Exception:
            pass
    return set()


def _save_exported(path: Path, new_ids: set[str]) -> None:
    existing = _load_exported(path)
    merged = existing | {str(i) for i in new_ids}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"ids": sorted(merged)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _remove_from_exported(path: Path, ids_to_remove: set[str]) -> None:
    """Remove IDs from the exported set so they get re-exported next time."""
    existing = _load_exported(path)
    cleaned = existing - {str(i) for i in ids_to_remove}
    if cleaned != existing:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"ids": sorted(cleaned)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def remove_from_exported(sku: str, model_code: str) -> None:
    """
    Remove a model from both Rozetka and Site exported sets.
    Called when a model gets a new/updated video.
    """
    base_model = model_code.split("_")[0] if "_" in model_code else model_code
    _remove_from_exported(_EXPORTED_SITE_PATH, {base_model, model_code, sku})

    try:
        rz_variants = _fetch_all_rozetka_variants()
        ids_to_remove = {
            str(v["rz_item_id"])
            for v in rz_variants
            if v.get("model") == base_model
        }
        if ids_to_remove:
            _remove_from_exported(_EXPORTED_ROZETKA_PATH, ids_to_remove)
            logger.info(
                "Removed %d Rozetka variant IDs for model %s from exported set",
                len(ids_to_remove), base_model,
            )
    except Exception as exc:
        logger.warning("Could not clean Rozetka exported set for model %s: %s", base_model, exc)


# ── Rozetka variants fetcher ──────────────────────────────────────────────────

def _fetch_all_rozetka_variants() -> list[dict]:
    """
    Fetch ALL product variants from Rozetka (no dedup by group).
    Each dict: {rz_item_id, article, model, name_ua, url}
    """
    if settings.USE_MOCKS:
        return [
            {
                "rz_item_id": 100001,
                "article": "26.2873_red_42(S)",
                "model": "26.2873",
                "name_ua": "Жіночий спортивний костюм 42(S) Червоний",
                "url": "https://rozetka.com.ua/100001/p100001",
            },
            {
                "rz_item_id": 100002,
                "article": "26.2861_beige_42(S)",
                "model": "26.2861",
                "name_ua": "Жіночий велюровий костюм 42(S) Бежевий",
                "url": "https://rozetka.com.ua/100002/p100002",
            },
            {
                "rz_item_id": 100003,
                "article": "26.2630_grey_44(M)",
                "model": "26.2630",
                "name_ua": "Жилетка жіноча коротка 44(M) Сірий",
                "url": "https://rozetka.com.ua/100003/p100003",
            },
        ]

    headers = {"Authorization": f"Bearer {settings.ROZETKA_API_KEY}"}
    all_items: list[dict] = []
    page = 1
    per_page = 100

    with httpx.Client(headers=headers, timeout=60, verify=False) as client:
        while True:
            resp = client.get(
                "https://api-seller.rozetka.com.ua/goods/all",
                params={"page": page, "per_page": per_page},
            )
            resp.raise_for_status()
            content = resp.json().get("content", {})
            items = content.get("items", [])
            if not items:
                break

            for item in items:
                article = item.get("article", "")
                model = article.split("_")[0].strip() if "_" in article else article.strip()
                all_items.append({
                    "rz_item_id": item["rz_item_id"],
                    "article":    article,
                    "model":      model,
                    "name_ua":    item.get("name_ua") or item.get("name", ""),
                    "url":        item.get("url", ""),
                })

            if page * per_page >= content.get("count", 0):
                break
            page += 1

    logger.info("Rozetka: fetched %d variants total", len(all_items))
    return all_items


# ── Excel helpers ─────────────────────────────────────────────────────────────

def _autofit(ws, df: pd.DataFrame) -> None:
    for ci, col in enumerate(df.columns, 1):
        w = max(
            len(str(col)),
            df[col].astype(str).map(len).max() if not df.empty else 0,
        )
        ws.column_dimensions[ws.cell(1, ci).column_letter].width = min(w + 4, 70)


# ── Public generators ─────────────────────────────────────────────────────────

def generate_rozetka_file(
    on_progress: Callable[[str], None] | None = None,
) -> tuple[Path, int]:
    """
    Generate Rozetka bulk-video-import Excel.
    Only includes variants whose rz_item_id was NOT in a previous export.

    Args:
        on_progress: optional callback for progress messages.

    Returns (file_path, new_rows_count).
    """
    _progress = on_progress or (lambda msg: None)

    # 1. Fetch YouTube videos
    _progress("[1/4] Завантажую список відео з YouTube...")
    yt_videos = sorted(fetch_channel_videos(), key=lambda v: v["published_at"])
    model_to_url: dict[str, str] = {}
    for v in yt_videos:
        if v["model"]:
            model_to_url[v["model"]] = v["url"]
    logger.info("YouTube models found: %d", len(model_to_url))
    _progress(f"[1/4] YouTube: знайдено {len(yt_videos)} відео, {len(model_to_url)} моделей")

    # 2. Fetch Rozetka variants
    _progress("[2/4] Завантажую товари з Розетки...")
    rz_variants = _fetch_all_rozetka_variants()
    _progress(f"[2/4] Розетка: знайдено {len(rz_variants)} варіантів")

    # 3. Match and build rows
    _progress("[3/4] Зіставляю моделі та формую рядки...")
    already = _load_exported(_EXPORTED_ROZETKA_PATH)

    rows: list[dict] = []
    new_ids: set[str] = set()
    skipped_no_video = 0
    skipped_already = 0

    for v in rz_variants:
        rz_id = str(v["rz_item_id"])
        yt_url = model_to_url.get(v["model"])

        if not yt_url:
            skipped_no_video += 1
            continue
        if rz_id in already:
            skipped_already += 1
            continue

        rows.append({
            "Код товару на ROZETKA":               v["rz_item_id"],
            "Посилання на товар на сайті ROZETKA": v["url"],
            "ID товару у вашому прайс-листі":      v["article"],
            "Назва товару":                        v["name_ua"],
            "Посилання на відео":                  yt_url,
        })
        new_ids.add(rz_id)

    _progress(
        f"[3/4] Нових: {len(rows)} | "
        f"Без відео: {skipped_no_video} | "
        f"Вже експортовано: {skipped_already}"
    )

    # 4. Write Excel
    _progress(f"[4/4] Записую Excel файл ({len(rows)} рядків)...")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = settings.temp_dir / f"rozetka_videos_{ts}.xlsx"
    df = pd.DataFrame(rows)

    with pd.ExcelWriter(str(out), engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Добавление видеообзора")
        _autofit(writer.sheets["Добавление видеообзора"], df)

    _save_exported(_EXPORTED_ROZETKA_PATH, new_ids)
    logger.info("Rozetka file: %d new rows → %s", len(rows), out)
    return out, len(rows)


def generate_site_file(
    on_progress: Callable[[str], None] | None = None,
) -> tuple[Path, int]:
    """
    Generate website video-mapping Excel: SKU | Посилання на відео.
    One row per model, only models NOT in a previous export.

    Args:
        on_progress: optional callback for progress messages.

    Returns (file_path, new_rows_count).
    """
    _progress = on_progress or (lambda msg: None)

    # 1. Fetch YouTube videos
    _progress("[1/3] Завантажую список відео з YouTube...")
    yt_videos = sorted(fetch_channel_videos(), key=lambda v: v["published_at"])

    model_to_url: dict[str, str] = {}
    for v in yt_videos:
        if v["model"]:
            model_to_url[v["model"]] = v["url"]
    _progress(f"[1/3] YouTube: знайдено {len(yt_videos)} відео, {len(model_to_url)} моделей")

    # 2. Match and build rows
    _progress("[2/3] Фільтрую нові моделі...")
    already = _load_exported(_EXPORTED_SITE_PATH)

    rows: list[dict] = []
    new_skus: set[str] = set()

    for model, url in model_to_url.items():
        if model in already:
            continue
        rows.append({"SKU": model, "Посилання на відео": url})
        new_skus.add(model)

    _progress(f"[2/3] Нових: {len(rows)} | Вже експортовано: {len(already)}")

    # 3. Write Excel
    _progress(f"[3/3] Записую Excel файл ({len(rows)} рядків)...")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = settings.temp_dir / f"site_videos_{ts}.xlsx"
    df = pd.DataFrame(rows)

    with pd.ExcelWriter(str(out), engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Відео для сайту")
        _autofit(writer.sheets["Відео для сайту"], df)

    _save_exported(_EXPORTED_SITE_PATH, new_skus)
    logger.info("Site file: %d new rows → %s", len(rows), out)
    return out, len(rows)
