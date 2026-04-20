"""
Generate a simple xlsx for price/stock update from SalesDrive YML feed.

Only fields available in the YML feed are included:
  Товар/Послуга, SKU, Ціна, Залишок на складі

For a full SalesDrive import template (with all columns + marketplace prices),
prepare the file manually and use the "Конвертація файлу цін" feature —
it keeps all columns as-is and filters only highlighted rows.
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
        "ID товару/послуги": "26.1881_black_48(XL)",
        "Товар/Послуга": "Женские велосипедки Aksan 26.1881 48(XL) Черный",
        "SKU": "26.1881_black_48(XL)",
        "Ціна": 345,
        "Знижка": "",
        "Ціна зі знижкою": "",
        "Залишок на складі": 3,
    },
    {
        "ID товару/послуги": "25.2779_black_46(L)",
        "Товар/Послуга": "Женские брюки Aksan 25.2779 46(L) Черный",
        "SKU": "25.2779_black_46(L)",
        "Ціна": 790,
        "Знижка": 87,
        "Ціна зі знижкою": 703,
        "Залишок на складі": 5,
    },
]


def _parse_yml_to_rows(content: bytes) -> list[dict]:
    root = ET.fromstring(content)
    shop = root.find("shop") or root

    rows: list[dict] = []
    for offer in shop.findall(".//offer"):
        name = offer.findtext("name") or offer.findtext("name_ua") or ""
        article = (
            offer.findtext("article")
            or offer.findtext("vendorCode")
            or offer.get("id", "")
        )
        price_raw = offer.findtext("price") or ""
        try:
            price = float(price_raw)
        except ValueError:
            price = ""

        # price у фіді = фінальна ціна, oldprice = оригінальна (до знижки)
        oldprice_raw = offer.findtext("oldprice") or ""
        base_price: float | str = price
        discount: float | str = ""
        final_price: float | str = ""

        if oldprice_raw and isinstance(price, float):
            try:
                old = float(oldprice_raw)
                if old > price:
                    base_price = old
                    discount = round(old - price, 2)
                    final_price = price
            except ValueError:
                pass

        stock_raw = offer.findtext("quantity_in_stock") or offer.findtext("quantity") or ""
        try:
            stock = int(stock_raw)
        except ValueError:
            stock = stock_raw

        rows.append({
            "ID товару/послуги": article,
            "Товар/Послуга": name,
            "SKU": article,
            "Ціна": base_price,
            "Знижка": discount,
            "Ціна зі знижкою": final_price,
            "Залишок на складі": stock,
        })

    rows.sort(key=lambda r: str(r.get("SKU", "")))
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

        _progress("[2/3] Паршу фід...")
        rows = _parse_yml_to_rows(resp.content)

    if not rows:
        return output_path, 0

    _progress(f"[3/3] Записую Excel ({len(rows)} рядків)...")
    df = pd.DataFrame(rows)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(str(output_path), engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Товари")
        _autofit(writer.sheets["Товари"], df)

    logger.info("Prices file saved: %s (%d rows)", output_path, len(rows))
    return output_path, len(rows)
