"""QuickBooks Online report JSON -> the engine's account_month and balance-sheet frames.

Input: the JSON that the read-only MCP tools return for get_profit_and_loss and get_balance_sheet with
summarize_column_by=Month (saved, redacted, under 01_connection/evidence/quickbooks/<date>/). Output: the same
DataFrame shape as abc_workbook_adapter.parse_wide_income_statement (one row per account, one column per month,
attrs carrying the section map and where each value came from), so every engine function runs unchanged.

Rules:
- A top-level group whose header matches a section header in the client config (e.g. Income -> income) is that
  section; its Summary row (e.g. Total Income) is the section total. Rows outside the configured sections (Gross
  Profit, Net Operating Income, Net Income, Other Expenses ...) are kept with no section, as the workbook parser does.
- Account names are QuickBooks fully qualified names: a leaf under a parent account is 'Parent:Child' (QuickBooks'
  own FullyQualifiedName convention), so 'Plants and Soil' under Income and under Expenses stay two accounts.
- Parent-account subtotals are checked (they must foot to their rows every month) but not emitted, so nothing is
  counted twice. A subtotal that does not foot is a STOP.
- A report whose shape is not what this adapter was written for (other report, not monthly, columns that are not
  calendar months, rows with the wrong number of cells, a name used twice) raises ShapeError: STOP, never a guess.
- An empty QuickBooks cell means no activity, which is 0. Text that is not a number is recorded in bad_cells.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import abc_workbook_adapter as engine


class ShapeError(ValueError):
    """The report is not shaped as expected; the run must stop."""


def read_report(path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ShapeError(f"QuickBooks report file not found: {path}. Check 'workbook' / 'balance_sheet_file' in the client config.")
    except json.JSONDecodeError as exc:
        raise ShapeError(f"{Path(path).name} is not valid JSON (line {exc.lineno}). Re-capture it with capture_monthly.py.")
    if not isinstance(data, dict):
        raise ShapeError(f"{Path(path).name}: expected a QuickBooks report object, got {type(data).__name__}.")
    return data


def month_columns(report: dict, report_name: str) -> list[tuple[int, pd.Timestamp]]:
    """[(ColData index, month)] for the report's month columns; raises ShapeError on any shape change."""
    header = report.get("Header")
    cols = (report.get("Columns") or {}).get("Column")
    if not isinstance(header, dict) or not isinstance(cols, list) or not isinstance(report.get("Rows"), dict):
        raise ShapeError(f"{report_name}: report shape changed: expected Header, Columns.Column and Rows; got keys {sorted(report)}.")
    if header.get("ReportName") != report_name:
        raise ShapeError(f"expected a {report_name} report, got ReportName={header.get('ReportName')!r}.")
    if header.get("SummarizeColumnsBy") != "Month":
        raise ShapeError(f"{report_name}: columns are summarized by {header.get('SummarizeColumnsBy')!r}, not 'Month'. "
                         "Re-run the report with summarize_column_by=Month.")
    if not cols or cols[0].get("ColType") != "Account":
        raise ShapeError(f"{report_name}: first column is {cols[0].get('ColType') if cols else None!r}, expected 'Account'.")
    out, seen = [], {}
    for j, c in enumerate(cols[1:], start=1):
        if c.get("ColTitle") == "Total" and j == len(cols) - 1:
            continue
        meta = {m.get("Name"): m.get("Value") for m in c.get("MetaData", [])}
        start, end = pd.to_datetime(meta.get("StartDate"), errors="coerce"), pd.to_datetime(meta.get("EndDate"), errors="coerce")
        if c.get("ColType") != "Money" or pd.isna(start) or pd.isna(end):
            raise ShapeError(f"{report_name}: column {j} ({c.get('ColTitle')!r}) is not a dated Money column.")
        month = start.to_period("M").to_timestamp()
        if start.day != 1 or end != (month + pd.offsets.MonthEnd(0)):
            raise ShapeError(f"{report_name}: column {c.get('ColTitle')!r} covers {meta.get('StartDate')}..{meta.get('EndDate')}, "
                             "not one whole calendar month. Request whole months (first to last day).")
        if month in seen:
            raise ShapeError(f"{report_name}: month {month:%b %Y} appears in two columns ({seen[month]} and {j}).")
        seen[month] = j
        out.append((j, month))
    if len(out) < 2:
        raise ShapeError(f"{report_name}: expected at least two monthly columns, found {len(out)}.")
    return out


def _value(cell):
    text = "" if cell is None else str(cell.get("value", ""))
    if text.strip() == "":
        return 0.0, None  # QuickBooks leaves a cell empty when there was no activity
    return engine.to_number(text)


def parse_report(report: dict, report_name: str, sections: dict | None = None, other_groups=()) -> pd.DataFrame:
    """One QuickBooks monthly report -> account x month frame (see module docstring).

    sections: {section id: (header label, total label)} as in the engine layout; {} for a Balance Sheet.
    other_groups: top-level group headers that are expected outside the sections (e.g. 'Other Expenses');
    any other unknown top-level group is kept with no section and reported in attrs['source_notes'] (WARN)."""
    sections = sections or {}
    is_pnl = bool(sections)
    months = month_columns(report, report_name)
    width = len(report["Columns"]["Column"])
    header_to_section = {h.casefold(): sid for sid, (h, _) in sections.items()}
    known_other = {g.casefold() for g in other_groups}
    rows, sec_of, cell_of, bad_cells, footing_off, notes = {}, {}, {}, [], [], []

    def read(coldata, label):
        if not isinstance(coldata, list) or len(coldata) != width:
            raise ShapeError(f"{report_name}: row {label!r} has {len(coldata) if isinstance(coldata, list) else 'no'} cells, "
                             f"expected {width} (one per column).")
        vals = {}
        for j, month in months:
            v, problem = _value(coldata[j])
            ref = f"{report_name}!{label}[{month:%b %Y}]"
            if problem:
                bad_cells.append((ref, label, f"{month:%b %Y}", problem))
            vals[month] = np.nan if v is None else v
        return vals

    def emit(name, vals, section):
        if name in rows:
            raise ShapeError(f"{report_name}: account name {name!r} appears twice; cannot tell the rows apart.")
        rows[name], sec_of[name] = vals, section
        for month in vals:
            cell_of[(name, month)] = f"{report_name}!{name}[{month:%b %Y}]"

    def walk(rowset, section, parents, depth):
        """Returns {month: sum of this level's rows} so the caller can foot its Summary."""
        total = {m: 0.0 for _, m in months}
        for r in (rowset or {}).get("Row", []):
            if not isinstance(r, dict):
                raise ShapeError(f"{report_name}: a row is {type(r).__name__}, expected an object.")
            if "ColData" in r:  # a plain account line
                label = str(r["ColData"][0].get("value", "")).strip() if r["ColData"] else ""
                name = ":".join(parents + [label])
                vals = read(r["ColData"], name)
                emit(name, vals, section)
                total = {m: total[m] + vals[m] for m in total}
                continue
            head = ((r.get("Header") or {}).get("ColData") or [{}])[0]
            label = str(head.get("value", "")).strip()
            summary = (r.get("Summary") or {}).get("ColData")
            group_section, group_parents = section, parents
            if depth == 0 and "Header" in r:
                if label.casefold() in header_to_section:
                    group_section = header_to_section[label.casefold()]
                elif is_pnl and label.casefold() not in known_other:
                    notes.append(f"QuickBooks group {label!r} is not mapped to a section in the client config; its lines reach "
                                 "the analysis only through the report's own totals (e.g. Net Income).")
            own = None
            if head.get("id"):  # a parent account: its children are named 'Parent:Child', as QuickBooks does
                group_parents = parents + [label]
                head_cols = (r.get("Header") or {}).get("ColData")
                # Postings made to the parent account itself are in the Header row's month cells.
                if isinstance(head_cols, list) and any(str((head_cols[j] or {}).get("value", "")).strip() for j, _ in months
                                                       if j < len(head_cols)):
                    own = read(head_cols, ":".join(group_parents))
                    emit(":".join(group_parents), own, group_section)
            inner = walk(r.get("Rows"), group_section, group_parents, depth + 1) if "Rows" in r else None
            if own is not None:
                inner = own if inner is None else {m: inner[m] + own[m] for m in inner}
            if summary is None:
                if inner is not None:
                    total = {m: total[m] + inner[m] for m in total}
                continue
            s_label = str(summary[0].get("value", "")).strip() if summary else ""
            s_vals = read(summary, s_label or label)
            if inner is not None:
                off = [(m, s_vals[m] - inner[m]) for m in inner if not abs(s_vals[m] - inner[m]) <= 0.005]
                footing_off.extend((s_label, m, d) for m, d in off)
            # Section totals and top-level lines are kept; parent-account subtotals are only checked.
            if depth == 0 or not is_pnl:
                emit(s_label, s_vals, None if depth == 0 else section)
            total = {m: total[m] + s_vals[m] for m in total}
        return total

    walk(report["Rows"], None, [], 0)
    if footing_off:
        lab, m, d = footing_off[0]
        raise ShapeError(f"{report_name}: {len(footing_off)} QuickBooks subtotal(s) do not foot to their rows; first: "
                         f"{lab!r} in {m:%b %Y} is off by {d:,.2f}. The export is inconsistent; re-run the report.")
    ordered = [m for _, m in sorted(months, key=lambda t: t[1])]
    data = pd.DataFrame.from_dict(rows, orient="index")[ordered] if rows else pd.DataFrame(columns=ordered)
    data.index.name, data.columns.name = "account", "month"
    data.attrs.update(sections=sec_of, sheet=report_name, row_of={a: i + 1 for i, a in enumerate(rows)}, col_of={},
                      cell_of=cell_of, bad_cells=bad_cells, blank_cells=[], source_notes=notes, source="qbo")
    return data


def _trim(frame: pd.DataFrame, first: pd.Timestamp) -> pd.DataFrame:
    attrs = dict(frame.attrs)
    out = frame.loc[:, frame.columns >= first]
    out.attrs.update(attrs)
    return out


def load(cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """(account_month, balance_sheet or None) for a client whose config says source: qbo.

    Leading months in which every P&L line is zero (QuickBooks returns the whole requested range, even before the
    company has any activity) are left out of both reports and named in source_notes, so they are not analysed as
    real zero-revenue months."""
    sections = {sid: (v["header"], v["total"]) for sid, v in cfg["sections"].items()}
    qbo = cfg.get("qbo") or {}
    am = parse_report(read_report(cfg["workbook_path"]), cfg["sheets"]["income_statement"], sections, qbo.get("other_groups", []))
    bs = None
    if cfg["sheets"].get("balance_sheet"):
        bs = parse_report(read_report(cfg["balance_sheet_path"]), cfg["sheets"]["balance_sheet"])
    active = [m for m in am.columns if am[m].fillna(0).ne(0).any()]
    if not active:
        raise ShapeError(f"{cfg['sheets']['income_statement']}: every line is zero in every month; nothing to analyse.")
    if qbo.get("trim_leading_zero_months", True) and active[0] > am.columns[0]:
        skipped = [m for m in am.columns if m < active[0]]
        am = _trim(am, active[0])
        am.attrs["source_notes"] = am.attrs["source_notes"] + [
            f"QuickBooks returned {len(skipped)} month(s) before {active[0]:%b %Y} ({skipped[0]:%b %Y} - {skipped[-1]:%b %Y}) with no "
            "activity on any line; they are left out, not analysed as zero months."]
        if bs is not None:
            bs = _trim(bs, active[0])
    return am, bs
