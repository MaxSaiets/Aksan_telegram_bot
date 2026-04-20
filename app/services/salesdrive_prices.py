"""
Generate an xlsx file for bulk price import into SalesDrive CRM.

Parses the SalesDrive YML feed and maps fields to the SalesDrive import format:
https://salesdrive.info/import/products

Column mapping from YML -> SalesDrive import columns:
  offer id          -> ID товару/послуги
  name              -> Товар/Послуга
  name_ua           -> Назва (UA)
  vendor            -> Виробник
  article/vendorCode -> SKU
  price             -> Ціна
  oldprice          -> якщо є — обчислює Знижку в %
  barcode           -> Штрихкод
  stock             -> Залишок на складі
  categoryId        -> ID категорії
  category name     -> Категорія
  description       -> Опис
  picture           -> Зображення (кілька через кому)
  url               -> Сторінка на сайті
  keywords          -> Ключові слова
  param[*]          -> Характеристика [Назва]
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

_MOCK_ROWS = [
    {
        "ID товару/послуги": "SD-001",
        "Товар/Послуга": "Костюм 40 червоний",
        "Назва (UA)": "Костюм 40 червоний",
        "Виробник": "Aksan",
        "SKU": "26.2873_red_40(S)",
        "Ціна": 1200.00,
        "Знижка": "",
        "Штрихкод": "",
        "Залишок на складі": "",
        "ID категорії": "10",
        "Категорія": "Костюми",
        "ID підкатегорії": "",
        "Підкатегорія": "",
        "Опис": "",
        "Зображення": "",
        "Сторінка на сайті": "",
        "Ключові слова": "",
    },
    {
        "ID товару/послуги": "SD-002",
        "Товар/Послуга": "Костюм 42 червоний",
        "Назва (UA)": "Костюм 42 червоний",
        "Виробник": "Aksan",
        "SKU": "26.2873_red_42(M)",
        "Ціна": 1200.00,
        "Знижка": "",
        "Штрихкод": "",
        "Залишок на складі": "",
        "ID категорії": "10",
        "Категорія": "Костюми",
        "ID підкатегорії": "",
        "Підкатегорія": "",
        "Опис": "",
        "Зображення": "",
        "Сторінка на сайті": "",
        "Ключові слова": "",
    },
]


def _parse_yml_to_rows(content: bytes) -> list[dict]:
    root = ET.fromstring(content)
    shop = root.find("shop")
    if shop is None:
        shop = root

    # Build category id->name map
    categories: dict[str, str] = {}
    category_parents: dict[str, str] = {}
    for cat in shop.findall(".//category"):
        cat_id = cat.get("id", "")
        parent_id = cat.get("parentId", "")
        categories[cat_id] = cat.text or ""
        if parent_id:
            category_parents[cat_id] = parent_id

    def _cat_name(cat_id: str) -> str:
        return categories.get(cat_id, "")

    def _parent_id(cat_id: str) -> str:
        return category_parents.get(cat_id, "")

    rows: list[dict] = []
    for offer in shop.findall(".//offer"):
        offer_id = offer.get("id", "")
        article = offer.findtext("article") or offer.findtext("vendorCode") or offer_id
        name = offer.findtext("name") or ""
        name_ua = offer.findtext("name_ua") or name
        vendor = offer.findtext("vendor") or offer.findtext("manufacturer") or ""
        price_str = offer.findtext("price") or ""
        oldprice_str = offer.findtext("oldprice") or ""
        barcode = offer.findtext("barcode") or offer.findtext("ean") or ""
        stock = offer.findtext("stock_quantity") or offer.findtext("quantity") or ""
        cat_id = offer.findtext("categoryId") or ""
        description = offer.findtext("description") or ""
        url = offer.findtext("url") or ""
        keywords = offer.findtext("keywords") or ""

        # Pictures — join multiple with comma
        pictures = [p.text.strip() for p in offer.findall("picture") if p.text]
        images = ", ".join(pictures)

        # Price / discount
        try:
            price = float(price_str) if price_str else ""
        except ValueError:
            price = ""
        discount = ""
        if price and oldprice_str:
            try:
                old = float(oldprice_str)
                if old > 0 and isinstance(price, float) and price < old:
                    discount = f"{round((old - price) / old * 100, 1)}%"
            except ValueError:
                pass

        # Category hierarchy
        parent = _parent_id(cat_id)
        if parent:
            top_cat_id = parent
            top_cat_name = _cat_name(parent)
            sub_cat_id = cat_id
            sub_cat_name = _cat_name(cat_id)
        else:
            top_cat_id = cat_id
            top_cat_name = _cat_name(cat_id)
            sub_cat_id = ""
            sub_cat_name = ""

        row: dict = {
            "ID товару/послуги": offer_id,
            "Товар/Послуга": name,
            "Назва (UA)": name_ua,
            "Виробник": vendor,
            "SKU": article,
            "Ціна": price,
            "Знижка": discount,
            "Штрихкод": barcode,
            "Залишок на складі": stock,
            "ID категорії": top_cat_id,
            "Категорія": top_cat_name,
            "ID підкатегорії": sub_cat_id,
            "Підкатегорія": sub_cat_name,
            "Опис": description,
            "Зображення": images,
            "Сторінка на сайті": url,
            "Ключові слова": keywords,
        }

        # Dynamic characteristic columns
        for param in offer.findall("param"):
            param_name = param.get("name", "").strip()
            if param_name:
                col = f"Характеристика [{param_name}]"
                if col in row:
                    row[col] = f"{row[col]}, {param.text or ''}"
                else:
                    row[col] = param.text or ""

        rows.append(row)

    logger.info("YML parsed: %d offers", len(rows))
    return rows


def _autofit(ws, df: pd.DataFrame) -> None:
    for ci, col in enumerate(df.columns, 1):
        width = max(
            len(str(col)),
            df[col].astype(str).map(len).max() if not df.empty else 0,
        )
        ws.column_dimensions[ws.cell(1, ci).column_letter].width = min(width + 4, 70)


def generate_prices_file(
    output_path: Path | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[Path, int]:
    _progress = on_progress or (lambda msg: None)

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

        _progress("[2/3] Парсю фід...")
        rows = _parse_yml_to_rows(resp.content)

    if not rows:
        return output_path, 0

    _progress(f"[3/3] Записую Excel ({len(rows)} рядків)...")
    df = pd.DataFrame(rows)

    # Ensure base columns appear first in a fixed order
    base_cols = [
        "ID товару/послуги", "Товар/Послуга", "Назва (UA)", "Виробник", "SKU",
        "Ціна", "Знижка", "Штрихкод", "Залишок на складі",
        "ID категорії", "Категорія", "ID підкатегорії", "Підкатегорія",
        "Опис", "Зображення", "Сторінка на сайті", "Ключові слова",
    ]
    extra_cols = [c for c in df.columns if c not in base_cols]
    df = df[base_cols + extra_cols]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(str(output_path), engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Товари")
        _autofit(writer.sheets["Товари"], df)

    logger.info("Prices file saved: %s (%d rows)", output_path, len(rows))
    return output_path, len(rows)
