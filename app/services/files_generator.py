"""
Generate incremental Excel files for Rozetka video import and website video mapping.
A model/category is included only if its latest YouTube video was not reported before,
or if the latest video changed since the last successful report.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from app.services.sku_parser import (
    allowed_sizes_for_category,
    extract_variant_size,
    variant_matches_category,
)
from app.services.youtube_catalog import fetch_channel_videos
from app.utils.logger import get_logger
from config import settings

logger = get_logger(__name__)

_ROZETKA_REPORT_STATE_PATH = Path("tmp/report_state/rozetka_latest.json")
_SITE_REPORT_STATE_PATH = Path("tmp/report_state/site_latest.json")


def _state_key(model: str, category: str) -> str:
    return f"{model}::{category}"


def _load_report_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(key): str(value) for key, value in data.items()}
    except Exception as exc:
        logger.warning("Could not load report state %s: %s", path, exc)
    return {}


def _save_report_state(path: Path, state: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _changed_video_map(video_map: dict[tuple[str, str], dict], state: dict[str, str]) -> dict[tuple[str, str], dict]:
    changed: dict[tuple[str, str], dict] = {}
    for key, video in video_map.items():
        current_url = str(video.get("url", ""))
        if current_url and state.get(_state_key(*key)) != current_url:
            changed[key] = video
    return changed


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

    import httpx

    from app.services.rozetka import _ROZETKA_BASE  # noqa: PLC2701

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


def generate_rozetka_file(on_progress: Callable[[str], None] | None = None) -> tuple:
    _progress = on_progress or (lambda msg: None)
    _progress("[1/4] Завантажую всі відео з YouTube...")
    video_map = _latest_video_map()
    state = _load_report_state(_ROZETKA_REPORT_STATE_PATH)
    changed_video_map = _changed_video_map(video_map, state)
    _progress(f"[1/4] Нових або оновлених model/category: {len(changed_video_map)}")

    _progress("[2/4] Завантажую всі варіанти з Rozetka...")
    variants = _fetch_all_rozetka_variants()
    grouped = _variant_groups_by_model(variants)
    _progress(f"[2/4] Rozetka: {len(variants)} варіантів")

    rows: list[dict] = []
    reported_state = dict(state)

    _progress("[3/4] Аналізую exact model/category і розкладаю відео по SKU...")
    for (model, category), video in changed_video_map.items():
        model_variants = grouped.get(model, [])
        available_sizes = {
            size
            for size in (extract_variant_size(item["article"]) for item in model_variants)
            if size is not None
        }
        allowed_sizes = allowed_sizes_for_category(category, available_sizes)
        if not allowed_sizes:
            continue

        matched = False
        for variant in model_variants:
            if not variant_matches_category(variant["article"], category, available_sizes):
                continue

            matched = True
            rows.append({
                "Код товару на ROZETKA": variant["rz_item_id"],
                "Посилання на товар на сайті ROZETKA": variant["url"],
                "ID товару у вашому прайс-листі": variant["article"],
                "Назва товару": variant["name_ua"],
                "Посилання на відео": video["url"],
            })

        if matched:
            reported_state[_state_key(model, category)] = str(video["url"])

    _progress(f"[3/4] Знайдено рядків для звіту: {len(rows)}")

    _progress("[4/4] Записую Excel...")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = settings.temp_dir / f"rozetka_videos_{ts}.xlsx"
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(str(out), engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Додавання відеоогляда")
        _autofit(writer.sheets["Додавання відеоогляда"], df)

    if rows:
        _save_report_state(_ROZETKA_REPORT_STATE_PATH, reported_state)

    logger.info("Rozetka file: %d rows -> %s", len(rows), out)
    return out, len(rows), len(changed_video_map)


def generate_site_file(on_progress: Callable[[str], None] | None = None) -> tuple:
    _progress = on_progress or (lambda msg: None)
    _progress("[1/4] Завантажую всі відео з YouTube...")
    video_map = _latest_video_map()
    state = _load_report_state(_SITE_REPORT_STATE_PATH)
    changed_video_map = _changed_video_map(video_map, state)
    _progress(f"[1/4] Нових або оновлених model/category: {len(changed_video_map)}")

    _progress("[2/4] Завантажую всі варіанти з Rozetka...")
    variants = _fetch_all_rozetka_variants()
    grouped = _variant_groups_by_model(variants)

    rows: list[dict] = []
    reported_state = dict(state)

    _progress("[3/4] Формую звіт для нових моделей і оновлених відео...")
    for (model, category), video in changed_video_map.items():
        model_variants = grouped.get(model, [])
        available_sizes = {
            size
            for size in (extract_variant_size(item["article"]) for item in model_variants)
            if size is not None
        }
        if not available_sizes:
            continue

        matched = False
        for variant in model_variants:
            article = variant["article"]
            if not variant_matches_category(article, category, available_sizes):
                continue

            matched = True
            rows.append({
                "SKU": article,
                "Посилання на відео": video["url"],
            })

        if matched:
            reported_state[_state_key(model, category)] = str(video["url"])

    _progress(f"[3/4] Знайдено рядків для звіту: {len(rows)}")

    _progress("[4/4] Записую Excel...")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = settings.temp_dir / f"site_videos_{ts}.xlsx"
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(str(out), engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Відео для сайту")
        _autofit(writer.sheets["Відео для сайту"], df)

    if rows:
        _save_report_state(_SITE_REPORT_STATE_PATH, reported_state)

    logger.info("Site file: %d rows -> %s", len(rows), out)
    return out, len(rows), len(changed_video_map)