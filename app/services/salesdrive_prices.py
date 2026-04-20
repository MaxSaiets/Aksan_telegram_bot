"""
Generate a simplified xlsx for bulk price update in SalesDrive CRM.

Columns per SalesDrive import spec:
  Товар/Послуга
  SKU
  Ціна
  Знижка                        (абсолютне або %)
  Ціна зі знижкою               (довідково, не імпортується)
  Залишок на складі
  Ціна [Ціна на маркетплейси]   ("Ціна [Тип ціни]")
  Ціна [Ціна на маркетплейси] - Знижка  ("Ціна [Тип ціни] - Знижка")
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

_MARKETPLACE_PRICE_TYPE = "Ціна на маркетплейси"

_MOCK_ROWS = [
    {
        "Товар/Послуга": "Костюм 40 червоний",
        "SKU": "26.2873_red_40(S)",
        "Ціна": 1200.00,
        "Знижка": "",
        "Ціна зі знижкою": 1200.00,
        "Залишок на складі": 5,
        f"Ціна [{_MARKETPLACE_PRICE_TYPE}]": 1400.00,
        f"Ціна [{_MARKETPLACE_PRICE_TYPE}] - Знижка": "",
    },
    {
        "Товар/Послуга": "Костюм 42 червоний",
        "SKU": "26.2873_red_42(M)",
        "Ціна": 1200.00,
        "Знижка": "5%",
        "Ціна зі знижкою": 1140.00,
        "Залишок на складі": 3,
        f"Ціна [{_MARKETPLACE_PRICE_TYPE}]": 1400.00,
        f"Ціна [{_MARKETPLACE_PRICE_TYPE}] - Знижка": "10%",
    },
]


def _to_float(val: str) -> float | None:
    try:
        return float(val.replace(",", ".").strip()) if val else None
    except ValueError:
        return None


def _calc_discounted(price: float | None, discount_str: str) -> float | None:
    if price is None:
        return None
    if not discount_str:
        return price
    d = discount_str.strip()
    try:
        if d.endswith("%"):
            pct = float(d[:-1])
            return round(price * (1 - pct / 100), 2)
        else:
            return round(price - float(d), 2)
    except ValueError:
        return price


def _parse_yml_to_rows(content: bytes) -> list[dict]:
    root = ET.fromstring(content)
    shop = root.find("shop") or root

    rows: list[dict] = []
    for offer in shop.findall(".//offer"):
        article = (
            offer.findtext("article")
            or offer.findtext("vendorCode")
            or offer.get("id", "")
        )
        name = offer.findtext("name_ua") or offer.findtext("name") or ""
        price = _to_float(offer.findtext("price") or "")
        old_price = _to_float(offer.findtext("oldprice") or "")
        stock = offer.findtext("stock_quantity") or offer.findtext("quantity") or ""

        # Main discount: derived from oldprice if present
        discount_str = ""
        if price is not None and old_price is not None and old_price > price:
            discount_str = f"{round((old_price - price) / old_price * 100, 1)}%"

        discounted = _calc_discounted(price, discount_str)

        # Additional prices — SalesDrive YML exports them as <price_type name="...">value</price_type>
        # or as nested <prices><price type="...">value</price></prices>
        marketplace_price: float | None = None
        marketplace_discount: str = ""

        for pt in offer.findall("price_type"):
            pt_name = (pt.get("name") or "").strip()
            if pt_name == _MARKETPLACE_PRICE_TYPE:
                marketplace_price = _to_float(pt.text or "")
                marketplace_discount = (pt.get("discount") or "").strip()

        if marketplace_price is None:
            for p in offer.findall(".//prices/price"):
                if (p.get("type") or "").strip() == _MARKETPLACE_PRICE_TYPE:
                    marketplace_price = _to_float(p.text or "")
                    marketplace_discount = (p.get("discount") or "").strip()

        rows.append({
            "Товар/Послуга": name,
            "SKU": article,
            "Ціна": price if price is not None else "",
            "Знижка": discount_str,
            "Ціна зі знижкою": discounted if discounted is not None else "",
            "Залишок на складі": stock,
            f"Ціна [{_MARKETPLACE_PRICE_TYPE}]": marketplace_price if marketplace_price is not None else "",
            f"Ціна [{_MARKETPLACE_PRICE_TYPE}] - Знижка": marketplace_discount,
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

        _progress("[2/3] Парсю фід...")
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
