"""
Generate an Excel report: SKU | YouTube URL | Model | Rozetka URL | Confidence
"""
from pathlib import Path
from datetime import datetime
from typing import Callable

import pandas as pd

from app.database.products_repo import get_all_with_sku
from app.utils.logger import get_logger
from config import settings

logger = get_logger(__name__)


def generate_report(
    output_path: Path | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> Path:
    """
    Query all matched products from DB and write an .xlsx file.

    Columns:
        SKU | Назва товару | YouTube URL | Модель | Rozetka URL | Впевненість (%)

    Returns the path to the generated file.
    """
    _progress = on_progress or (lambda msg: None)

    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = settings.temp_dir / f"report_{ts}.xlsx"

    _progress("[1/3] Завантажую дані з бази...")
    products = get_all_with_sku()

    if not products:
        logger.warning("No matched products in DB — report will be empty")

    # Deduplicate by SKU — keep the latest entry (by created_at)
    _progress(f"[2/3] Обробляю {len(products)} записів (дедуплікація)...")
    sku_map: dict[str, dict] = {}
    for p in sorted(products, key=lambda x: x.get("created_at", "")):
        sku = p.get("sku", "")
        if sku:
            sku_map[sku] = p

    rows = [
        {
            "SKU":              p.get("sku", ""),
            "Назва товару":     p.get("product_name", ""),
            "YouTube URL":      p.get("youtube_url", ""),
            "Модель":           p.get("model_name", ""),
            "Rozetka URL":      p.get("rozetka_url", ""),
            "Впевненість (%)":  round((p.get("match_confidence") or 0) * 100, 1),
        }
        for p in sku_map.values()
    ]

    _progress(f"[3/3] Записую Excel файл ({len(rows)} рядків)...")
    df = pd.DataFrame(rows)

    with pd.ExcelWriter(str(output_path), engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Товари")

        # Auto-fit column widths
        ws = writer.sheets["Товари"]
        for col_idx, col in enumerate(df.columns, start=1):
            max_len = max(
                len(str(col)),
                df[col].astype(str).map(len).max() if not df.empty else 0,
            )
            ws.column_dimensions[ws.cell(1, col_idx).column_letter].width = (
                min(max_len + 4, 80)
            )

    logger.info("Excel report saved: %s (%d rows)", output_path, len(rows))
    return output_path
