"""Shared reviewer-friendly layout for every workbook we write: header in row 1, fitted widths, frozen panes,
filters, number formats and landscape fit-to-width printing. Formatting only; it never changes a cell's value.
"""
from __future__ import annotations
from datetime import date, datetime
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

MONEY = "#,##0;[Red](#,##0)"
PCT = "0.0%;[Red](0.0%)"
DATE = "mmm yyyy"
PLAIN = "0"
MAX_WIDTH, MIN_WIDTH = 50, 8
HEAD = PatternFill("solid", fgColor="1F3864")


def _is_pct(header) -> bool:
    return isinstance(header, str) and (header.endswith("_pct") or header.startswith("share_of"))


def _shown_len(value, fmt) -> int:
    """Approximate display width of a cell after formatting."""
    if value is None:
        return 0
    if isinstance(value, (datetime, date)):
        return 8
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if fmt == PCT:
            return len(f"{value * 100:.1f}%") + 2
        if fmt == PLAIN:
            return len(f"{value:.0f}")
        return len(f"{abs(value):,.0f}") + 2
    return max(len(line) for line in str(value).splitlines() or [""])


def polish_sheet(ws, wrap=(), formats=None, table=True):
    """Lay out one sheet whose header is row 1. `wrap` = headers of note/question columns (the only wrapped ones);
    `formats` = {header: number_format} overrides; numeric cells default to MONEY, `*_pct`/`share_of*` to PCT."""
    formats = formats or {}
    headers = [c.value for c in ws[1]]
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), HEAD
        c.alignment = Alignment(vertical="top", wrap_text=c.value in wrap)
        if isinstance(c.value, (datetime, date)):
            c.number_format = DATE
    for i, header in enumerate(headers, 1):
        fmt_default = formats.get(header, PCT if _is_pct(header) else MONEY)
        width = len(str(header)) if not isinstance(header, (datetime, date)) else 8
        for (cell,) in ws.iter_rows(min_row=2, min_col=i, max_col=i):
            v = cell.value
            if isinstance(v, (datetime, date)):
                cell.number_format = DATE
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                cell.number_format = fmt_default
            cell.alignment = Alignment(vertical="top", wrap_text=header in wrap)
            width = max(width, _shown_len(v, cell.number_format))
        ws.column_dimensions[get_column_letter(i)].width = max(MIN_WIDTH, min(MAX_WIDTH, width + 2))
    ws.freeze_panes = "B2"
    if table and ws.max_row > 1:
        ws.auto_filter.ref = ws.dimensions
    ws.print_title_rows = "1:1"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    return ws


def drop_empty(wb):
    """Remove columns with no header and no values, then sheets with no values at all."""
    for ws in list(wb.worksheets):
        for col in range(ws.max_column, 0, -1):
            if all(c.value in (None, "") for (c,) in ws.iter_rows(min_col=col, max_col=col)):
                ws.delete_cols(col)
        if len(wb.worksheets) > 1 and all(c.value in (None, "") for row in ws.iter_rows() for c in row):
            wb.remove(ws)
    return wb
