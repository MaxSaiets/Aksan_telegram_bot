"""
Generate full SalesDrive import xlsx from YML feed.

All official SalesDrive import columns are included.
Fields filled from YML; empty columns left blank for manual edit.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Callable

import httpx
import pandas as pd

from app.utils.logger import get_logger
from config import settings

logger = get_logger(__name__)

COLUMNS = [
    "ID товару/послуги",
    "Товар/Послуга",
    "Назва (UA)",
    "Назва для документів",
    "Виробник",
    "SKU",
    "Ціна",
    "Знижка",
    "Ціна зі знижкою",
    "Період знижки від",
    "Період знижки до",
    "Собівартість",
    "Штрихкод",
    "Залишок на складі",
    "Комплект",
    "ID основного товару різновиду",
    "Опис",
    "Опис (UA)",
    "Зображення",
    "Сторінка на сайті",
    "Нотатка",
    "Ключові слова",
    "ID категорії",
    "Категорія",
    "Структура категорій",
    "Ціна [Ціна на маркетплейси]",
    "Ціна [Ціна на маркетплейси] - Знижка",
]

_MOCK_ROWS = [
    {
        "ID товару/послуги": "118017",
        "Товар/Послуга": "Женские велосипедки Aksan 26.1881 48(XL) Черный",
        "Назва (UA)": "Жіночі велосипедки Aksan 26.1881 48(XL) Чорний",
        "Назва для документів": "",
        "Виробник": "Aksan",
        "SKU": "26.1881_black_48(XL)",
        "Ціна": 345,
        "Знижка": "",
        "Ціна зі знижкою": "",
        "Період знижки від": "",
        "Період знижки до": "",
        "Собівартість": "",
        "Штрихкод": "",
        "Залишок на складі": 3,
        "Комплект": "",
        "ID основного товару різновиду": "118017",
        "Опис": "",
        "Опис (UA)": "",
        "Зображення": "",
        "Сторінка на сайті": "",
        "Нотатка": "",
        "Ключові слова": "",
        "ID категорії": "33243126",
        "Категорія": "Лосини жіночі",
        "Структура категорій": "Лосини жіночі",
        "Ціна [Ціна на маркетплейси]": "",
        "Ціна [Ціна на маркетплейси] - Знижка": "",
    },
]


def _parse_yml_to_rows(content: bytes) -> list[dict]:
    root = ET.fromstring(content)
    shop = root.find("shop") or root

    categories: dict[str, str] = {}
    for cat in shop.findall(".//category"):
        categories[cat.get("id", "")] = cat.text or ""

    rows: list[dict] = []
    for offer in shop.findall(".//offer"):
        offer_id = offer.get("id", "")
        group_id = offer.get("group_id", offer_id)

        name = offer.findtext("name") or ""
        name_ua = offer.findtext("name_ua") or name
        vendor = offer.findtext("vendor") or offer.findtext("manufacturer") or ""
        article = offer.findtext("article") or offer.findtext("vendorCode") or offer_id

        price_raw = offer.findtext("price") or ""
        try:
            price = float(price_raw)
        except ValueError:
            price = ""

        stock_raw = offer.findtext("quantity_in_stock") or offer.findtext("quantity") or ""
        try:
            stock = int(stock_raw)
        except ValueError:
            stock = stock_raw

        cat_id = offer.findtext("categoryId") or ""
        cat_name = categories.get(cat_id, "")

        description = offer.findtext("description") or ""
        description_ua = offer.findtext("description_ua") or ""
        url = offer.findtext("url") or ""

        pictures = [p.text.strip() for p in offer.findall("picture") if p.text]
        images = ", ".join(pictures)

        rows.append({
            "ID товару/послуги": group_id,
            "Товар/Послуга": name,
            "Назва (UA)": name_ua,
            "Назва для документів": "",
            "Виробник": vendor,
            "SKU": article,
            "Ціна": price,
            "Знижка": "",
            "Ціна зі знижкою": "",
            "Період знижки від": "",
            "Період знижки до": "",
            "Собівартість": "",
            "Штрихкод": "",
            "Залишок на складі": stock,
            "Комплект": "",
            "ID основного товару різновиду": group_id,
            "Опис": description,
            "Опис (UA)": description_ua,
            "Зображення": images,
            "Сторінка на сайті": url,
            "Нотатка": "",
            "Ключові слова": "",
            "ID категорії": cat_id,
            "Категорія": cat_name,
            "Структура категорій": cat_name,
            "Ціна [Ціна на маркетплейси]": "",
            "Ціна [Ціна на маркетплейси] - Знижка": "",
        })

    logger.info("YML parsed: %d offers", len(rows))
    return rows


def _autofit(ws, df: pd.DataFrame) -> None:
    for ci, col in enumerate(df.columns, 1):
        width = max(
            len(str(col)),
            df[col].astype(str).map(len).max() if not df.empty else 0,
        )
        ws.column_dimensions[ws.cell(1, ci).column_letter].width = min(width + 4, 60)


def generate_prices_file(
    output_path: Path | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[Path, int]:
    _progress = on_progress or (lambda _: None)

    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = settings.temp_dir / f"salesdrive_prices_{ts}.xlsx"

    if settings.USE_MOCKS:
        _progress("[MOCK] Використовую тестові дані...")
        rows = list(_MOCK_ROWS)
    else:
        if not settings.SALESDRIVE_YML_URL:
            raise ValueError("SALESDRIVE_YML_URL не налаштовано")

        _progress("[1/3] Завантажую YML фід з SalesDrive...")
        resp = httpx.get(settings.SALESDRIVE_YML_URL, timeout=60, follow_redirects=True)
        resp.raise_for_status()

        _progress("[2/3] Парсую фід...")
        rows = _parse_yml_to_rows(resp.content)

    if not rows:
        return output_path, 0

    _progress(f"[3/3] Записую Excel ({len(rows)} рядків)...")
    df = pd.DataFrame(rows, columns=COLUMNS)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(str(output_path), engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Товари")
        _autofit(writer.sheets["Товари"], df)

    logger.info("Prices file saved: %s (%d rows)", output_path, len(rows))
    return output_path, len(rows)
