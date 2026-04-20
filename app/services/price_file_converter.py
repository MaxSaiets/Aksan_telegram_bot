"""
Filter an xlsx prices file: keep only rows where any cell has a non-default
background fill color (i.e. rows the user manually highlighted).

Default/empty fills are:
  - patternType == "none"
  - fgColor in (00000000, FFFFFFFF, FF000000) — transparent or white/black defaults
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from openpyxl import Workbook
from openpyxl.styles.fills import PatternFill
from openpyxl.utils import get_column_letter

from app.utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_COLORS = {"00000000", "FFFFFFFF", "FF000000"}


def _is_colored(fill) -> bool:
    if fill is None:
        return False
    if not isinstance(fill, PatternFill):
        return False
    if fill.patternType in (None, "none"):
        return False
    color = fill.fgColor
    if color is None:
        return False
    # theme/index colors are non-default
    if color.type in ("theme", "indexed"):
        return True
    rgb = (color.rgb or "").upper()
    return bool(rgb) and rgb not in _DEFAULT_COLORS


def _row_is_highlighted(ws, row_idx: int) -> bool:
    for cell in ws[row_idx]:
        if _is_colored(cell.fill):
            return True
    return False


def filter_colored_rows(input_path: Path, output_path: Path) -> int:
    """
    Read input_path xlsx, write only highlighted rows to output_path.
    Returns the number of kept rows (excluding header).
    """
    wb_in = load_workbook(input_path)
    ws_in = wb_in.active

    wb_out = Workbook()
    ws_out = wb_out.active
    ws_out.title = ws_in.title

    max_col = ws_in.max_column

    # Copy header (row 1) always
    header_row = [ws_in.cell(1, c).value for c in range(1, max_col + 1)]
    ws_out.append(header_row)

    kept = 0
    for row_idx in range(2, ws_in.max_row + 1):
        if _row_is_highlighted(ws_in, row_idx):
            values = [ws_in.cell(row_idx, c).value for c in range(1, max_col + 1)]
            ws_out.append(values)
            kept += 1

    # Auto-fit column widths
    for col_idx in range(1, max_col + 1):
        letter = get_column_letter(col_idx)
        max_len = len(str(header_row[col_idx - 1] or ""))
        for row_idx in range(2, ws_out.max_row + 1):
            val = ws_out.cell(row_idx, col_idx).value
            max_len = max(max_len, len(str(val or "")))
        ws_out.column_dimensions[letter].width = min(max_len + 4, 60)

    wb_out.save(str(output_path))
    logger.info("Converted: %d highlighted rows kept -> %s", kept, output_path.name)
    return kept
