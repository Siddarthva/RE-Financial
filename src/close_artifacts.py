"""Engine-side artifacts for the Close Review Workspace: intake checks, flux table, workbook locator.

All arithmetic lives here (and in the existing engine). The UI only reads the JSON these produce.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

# Flux rule: a line item is flagged when it moves by at least FLUX_MIN_DOLLARS *and* FLUX_MIN_PCT
# (or has no % because the prior month was zero). Sign flips use a lower dollar floor.
FLUX_MIN_DOLLARS = 5000.0
FLUX_MIN_PCT = 0.10
FLUX_SIGN_FLIP_DOLLARS = 1000.0

REASONS = {
    "NEW_ITEM": ("high", "Prior month was zero; current month is not. Flagged when |$Δ| >= ${d:,.0f}."),
    "DROPPED_ITEM": ("high", "Current month is zero; prior month was not. Flagged when |$Δ| >= ${d:,.0f}."),
    "SIGN_FLIP": ("high", "Sign changed versus prior month. Flagged when |$Δ| >= ${f:,.0f}."),
    "LARGE_MOVE": ("medium", "|$Δ| >= ${d:,.0f} and |%Δ| >= {p:.0%}."),
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _layout(cfg: dict) -> dict:
    return {"sheet": cfg["sheets"]["income_statement"], "header_label": cfg["layout"]["header_label"],
            "month_format": cfg["layout"]["month_format"],
            "sections": {sid: (v["header"], v["total"]) for sid, v in cfg["sections"].items()}}


def locate(cfg: dict) -> dict:
    """Scan the income-statement sheet and return header/month/account cell positions (read-only)."""
    lay = _layout(cfg)
    wb = load_workbook(cfg["workbook_path"], read_only=True, data_only=True)
    try:
        ws = wb[lay["sheet"]]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
    finally:
        wb.close()
    header_row = next((i for i in range(min(15, len(rows))) if lay["header_label"] in [str(v) for v in rows[i]]), None)
    if header_row is None:
        return {"sheet": lay["sheet"], "header_row": None, "account_col": None, "month_cols": {}, "accounts": {}}
    account_col = [str(v) for v in rows[header_row]].index(lay["header_label"])
    month_cols = {}
    for j, v in enumerate(rows[header_row]):
        if j == account_col or v is None:
            continue
        p = pd.to_datetime(str(v), format=lay["month_format"], errors="coerce")
        if pd.notna(p):
            month_cols[f"{p:%Y-%m}"] = j
    headers = {h.casefold(): sid for sid, (h, _) in lay["sections"].items()}
    totals = {t.casefold(): sid for sid, (_, t) in lay["sections"].items()}
    accounts, section = {}, None
    for i in range(header_row + 1, len(rows)):
        name = rows[i][account_col] if account_col < len(rows[i]) else None
        if name is None or (isinstance(name, float) and pd.isna(name)):
            name = rows[i][0]
        if name is None:
            continue
        name = str(name).strip()
        if name.casefold() in headers:
            section = headers[name.casefold()]
            continue
        if section is not None and totals.get(name.casefold()) == section:
            section_for_row, section = section, None
        else:
            section_for_row = section
        accounts.setdefault((name, section_for_row), i + 1)
    return {"sheet": lay["sheet"], "header_row": header_row + 1, "account_col": account_col,
            "month_cols": month_cols, "accounts": accounts}


def cell_ref(loc: dict, account: str, section: str | None, month: str) -> str | None:
    row = loc["accounts"].get((account, section)) or next(
        (r for (a, _), r in loc["accounts"].items() if a == account), None)
    col = loc["month_cols"].get(month)
    if row is None or col is None:
        return None
    return f"{loc['sheet']}!{get_column_letter(col + 1)}{row}"


def build_flux(packet: dict, loc: dict) -> dict:
    month, prior = packet["latest_month"], packet["prior_month"]
    items = []
    for account, v in packet["line_items"].items():
        cur, pri = v.get("value") or 0.0, v.get("prior_value") or 0.0
        delta = v.get("mom_change")
        if delta is None:
            continue
        code = None
        if pri == 0 and cur != 0 and abs(delta) >= FLUX_MIN_DOLLARS:
            code = "NEW_ITEM"
        elif cur == 0 and pri != 0 and abs(delta) >= FLUX_MIN_DOLLARS:
            code = "DROPPED_ITEM"
        elif pri * cur < 0 and abs(delta) >= FLUX_SIGN_FLIP_DOLLARS:
            code = "SIGN_FLIP"
        elif abs(delta) >= FLUX_MIN_DOLLARS and v.get("mom_pct") is not None and abs(v["mom_pct"]) >= FLUX_MIN_PCT:
            code = "LARGE_MOVE"
        if not code:
            continue
        sev, rule = REASONS[code]
        items.append({
            "account": account, "section": v.get("section"), "reason_code": code, "severity": sev,
            "metric": f"{account} ({v.get('section')})", "current": cur, "prior": pri,
            "dollar_change": delta, "pct_change": v.get("mom_pct"),
            "source_cell_current": cell_ref(loc, account, v.get("section"), month),
            "source_cell_prior": cell_ref(loc, account, v.get("section"), prior),
            "threshold_rule": rule.format(d=FLUX_MIN_DOLLARS, f=FLUX_SIGN_FLIP_DOLLARS, p=FLUX_MIN_PCT),
        })
    items.sort(key=lambda r: abs(r["dollar_change"]), reverse=True)
    return {"client": packet.get("client"), "period": month, "prior_period": prior,
            "rule": {"min_dollars": FLUX_MIN_DOLLARS, "min_pct": FLUX_MIN_PCT, "sign_flip_dollars": FLUX_SIGN_FLIP_DOLLARS},
            "items": items}


def build_intake(cfg: dict, loc: dict, monthly: pd.DataFrame, account_month: pd.DataFrame) -> dict:
    """Workbook card data: sheets, period range, hash, and pass/fail checks with cell refs."""
    path = Path(cfg["workbook_path"])
    wb = load_workbook(path, read_only=True)
    sheets = list(wb.sheetnames)
    wb.close()
    checks = []

    def add(name, ok, ref, detail=""):
        checks.append({"check": name, "passed": bool(ok), "cell_ref": ref, "detail": detail})

    sheet = loc["sheet"]
    add("Income statement sheet present", sheet in sheets, sheet)
    hr = loc["header_row"]
    add("Header row found", hr is not None, f"{sheet}!{get_column_letter(loc['account_col'] + 1)}{hr}" if hr else sheet,
        cfg["layout"]["header_label"])
    cols = sorted(loc["month_cols"].values())
    contiguous = bool(cols) and cols == list(range(cols[0], cols[-1] + 1))
    add("Month columns contiguous", contiguous,
        f"{sheet}!{get_column_letter(cols[0] + 1)}{hr}:{get_column_letter(cols[-1] + 1)}{hr}" if cols and hr else sheet,
        f"{len(cols)} month columns")
    latest = f"{monthly['month'].iloc[-1]:%Y-%m}"
    for key, label in cfg["totals"].items():
        ref = cell_ref(loc, label, None, latest)
        add(f"Total row present: {label}", ref is not None, ref or sheet, key)
    m = monthly.iloc[-1]
    gp_ok = abs(m["revenue"] - m["cost_of_goods_sold"] - m["gross_profit"]) <= 0.005
    add("Gross profit = revenue - COGS (latest month)", gp_ok, cell_ref(loc, cfg["totals"]["gross_profit"], None, latest) or sheet)
    oi_ok = abs(m["gross_profit"] - m["operating_expenses"] - m["operating_income"]) <= 0.005
    add("Operating income = gross profit - opex (latest month)", oi_ok,
        cell_ref(loc, cfg["totals"]["operating_income"], None, latest) or sheet)
    return {
        "workbook": path.name, "sha256": sha256_file(path), "sheets_detected": sheets,
        "period_start": f"{monthly['month'].iloc[0]:%Y-%m}", "period_end": latest, "months": len(monthly),
        "checks": checks, "status": "pass" if all(c["passed"] for c in checks) else "fail",
    }


def build_tables(cfg: dict, account_month: pd.DataFrame, engine) -> dict:
    """Per-month tables for the Financial Analysis tabs: revenue by stream and opex by category."""
    def clean(x):
        return None if pd.isna(x) else round(float(x), 2)

    months = [f"{m:%Y-%m}" for m in account_month.columns]
    sections = account_month.attrs.get("sections", {})
    streams = {a: {f"{m:%Y-%m}": clean(account_month.loc[a, m]) for m in account_month.columns}
               for a in account_month.index if sections.get(a) == "income"}
    trends = engine.build_expense_category_trends(account_month, cfg["subtotal_rows"])
    rollup = engine.build_category_rollup(trends, cfg["account_to_category"])
    cats: dict = {}
    for r in rollup.itertuples():
        cats.setdefault(r.category, {})[f"{r.month:%Y-%m}"] = clean(r.amount)
    return {"months": months, "revenue_by_stream": streams, "opex_by_category": cats}
