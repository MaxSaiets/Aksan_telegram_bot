"""
Filter an xlsx file: keep only rows where any cell has a non-default
background fill OR font color (i.e. rows the user manually highlighted).
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook, Workbook
from openpyxl.styles.fills import GradientFill, PatternFill
from openpyxl.utils import get_column_letter

from app.utils.logger import get_logger

logger = get_logger(__name__)

_NO_COLOR_RGB = {"00000000", "FFFFFFFF", "FF000000"}
_AUTO_INDEXED = {64}
_DEFAULT_THEME = {0, 1}


def _color_is_set(color) -> bool:
    if color is None:
        return False
    t = getattr(color, "type", None)
    if t == "theme":
        return getattr(color, "theme", None) not in _DEFAULT_THEME
    if t == "indexed":
        return getattr(color, "indexed", 64) not in _AUTO_INDEXED
    rgb = (getattr(color, "rgb", None) or "").upper()
    return bool(rgb) and rgb not in _NO_COLOR_RGB


def _fill_is_colored(fill) -> bool:
    if fill is None:
        return False
    if isinstance(fill, GradientFill):
        return True
    if not isinstance(fill, PatternFill):
        return False
    if fill.patternType in (None, "none"):
        return False
    return _color_is_set(fill.fgColor) or _color_is_set(fill.bgColor)


def _font_is_colored(font) -> bool:
    if font is None:
        return False
    return _color_is_set(getattr(font, "color", None))


def _row_is_highlighted(row_cells) -> bool:
    for cell in row_cells:
        if _fill_is_colored(cell.fill):
            return True
        if _font_is_colored(cell.font):
            return True
    return False


def filter_colored_rows(input_path: Path, output_path: Path) -> int:
    wb_in = load_workbook(input_path)
    ws_in = wb_in.active

    wb_out = Workbook()
    ws_out = wb_out.active
    ws_out.title = ws_in.title

    max_col = ws_in.max_column
    col_widths = [0] * max_col

    def _append_row(values: list) -> None:
        ws_out.append(values)
        for i, v in enumerate(values):
            col_widths[i] = max(col_widths[i], len(str(v or "")))

    # Header — always kept
    header = [ws_in.cell(1, c).value for c in range(1, max_col + 1)]
    _append_row(header)

    kept = 0
    for row in ws_in.iter_rows(min_row=2):
        if _row_is_highlighted(row):
            _append_row([cell.value for cell in row])
            kept += 1

    for i, width in enumerate(col_widths, 1):
        ws_out.column_dimensions[get_column_letter(i)].width = min(width + 4, 60)

    wb_out.save(str(output_path))
    logger.info("Converted: %d highlighted rows -> %s", kept, output_path.name)
    return kept
