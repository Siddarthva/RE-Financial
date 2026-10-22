"""Adapter for wide-format monthly income statements (one column per month).

Defaults match the ABC Inc workbook. Other clients pass their labels from clients/<client>/config.yaml
(see src/run_client.py), so a new client needs a config file, not a code change.
"""
import re
from pathlib import Path
import pandas as pd
import numpy as np
from openpyxl.utils import get_column_letter

# Canonical section ids used throughout the engine, independent of a client's labels.
SECTIONS = ("income", "cost of goods sold", "operating expenses")

ABC_LAYOUT = {
    "sheet": "Income Statement",
    "header_label": "Account",
    "month_format": "%b %Y",
    # canonical section id -> (header row label, total row label) in the source sheet
    "sections": {
        "income": ("Income", "Total Income"),
        "cost of goods sold": ("Cost of Goods Sold", "Total Cost of Goods Sold"),
        "operating expenses": ("Operating Expenses", "Total Operating Expenses"),
    },
}
ABC_TOTALS = {
    "revenue": "Total Income",
    "cost_of_goods_sold": "Total Cost of Goods Sold",
    "gross_profit": "Gross Profit",
    "operating_expenses": "Total Operating Expenses",
    "operating_income": "Operating Income",
    "net_income": "Net Income",
}
# Nested block headers and subtotals inside Operating Expenses; their children are the detail rows.
ABC_SUBTOTAL_ROWS = ("S & M Payroll", "Total S & M Payroll", "Marketing", "Total Marketing")
# Balance Sheet: same wide layout, month-end date headers, no P&L sections.
ABC_BS_LAYOUT = {"sheet": "Balance Sheet", "header_label": "Account", "month_format": "%d %b %Y", "sections": {}}
ABC_CASH_ROW = "Total Cash and Cash Equivalents"

_MONEY_TEXT = re.compile(r"^\s*(-)?\s*\(?\s*(-)?\s*[$€£₹]?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*\)?\s*$")


def to_number(value):
    """A cell value as a finite float, or (None, reason). Accepts '$1,234.50', '(1,234)', '-$1,234'."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None, "blank"
    if isinstance(value, bool):
        return None, f"not a number: {value!r}"
    if isinstance(value, (int, float, np.integer, np.floating)):
        return (float(value), None) if np.isfinite(value) else (None, f"not a finite number: {value!r}")
    text = str(value).strip()
    if not text:
        return None, "blank"
    m = _MONEY_TEXT.match(text)
    if m and text.count("(") == text.count(")"):
        n = float(m.group(3).replace(",", ""))
        return (-n if (m.group(1) or m.group(2) or text.startswith("(")) else n), None
    return None, f"text, not a number: {text[:20]!r}"


def cell_name(account_month, account, month):
    """'Income Statement!C14' for a parsed value, or None if the parser did not record the position."""
    cell_of = account_month.attrs.get("cell_of")
    if cell_of is not None:  # long-format and QuickBooks sources record each value's position directly
        return cell_of.get((account, month))
    rows, cols = account_month.attrs.get("row_of", {}), account_month.attrs.get("col_of", {})
    if account not in rows or month not in cols:
        return None
    return f"{account_month.attrs.get('sheet')}!{cols[month]}{rows[account]}"


def parse_wide_income_statement(path, layout=None):
    """One row per account, one column per month. attrs carry the section map, each value's source cell
    (row_of/col_of), and the cells that could not be read as numbers (bad_cells) or were blank inside a
    row that has values elsewhere (blank_cells). Bad cells become NaN; callers decide whether to stop."""
    layout = layout or ABC_LAYOUT
    sheet, header_label = layout["sheet"], layout["header_label"]
    # keep_default_na=False: pandas would otherwise turn text like 'n/a', 'NA' or 'NaN' into a silent blank.
    raw = pd.read_excel(path, sheet_name=sheet, header=None, keep_default_na=False)
    raw = raw.mask(raw.eq(""))  # truly empty cells are blank again
    header_row = None
    for i in range(min(15, len(raw))):
        vals = raw.iloc[i].astype(str).tolist()
        if header_label in vals:
            header_row = i
            break
    if header_row is None:
        raise ValueError(f"Could not find the '{header_label}' header row in {sheet}.")
    headers = raw.iloc[header_row].tolist()
    account_col = headers.index(header_label)
    date_cols = []
    for j, value in enumerate(headers):
        if j == account_col or pd.isna(value):
            continue
        parsed = pd.to_datetime(str(value), format=layout["month_format"], errors="coerce")
        if pd.notna(parsed):
            date_cols.append((j, parsed.to_period("M").to_timestamp()))
    if len(date_cols) < 2:
        raise ValueError(f"Expected at least two monthly columns in {sheet}.")
    seen = {}
    for j, month in date_cols:
        if month in seen:
            raise ValueError(f"{sheet}: month {month:%b %Y} appears twice, in cells {get_column_letter(seen[month] + 1)}{header_row + 1} "
                             f"and {get_column_letter(j + 1)}{header_row + 1}. Remove the duplicate column.")
        seen[month] = j
    headers_to_section = {h.casefold(): sid for sid, (h, _) in layout["sections"].items()}
    totals_to_section = {t.casefold(): sid for sid, (_, t) in layout["sections"].items()}
    rows = []
    sections, row_of, bad_cells, blank_cells = {}, {}, [], []
    section = None
    for i in range(header_row + 1, len(raw)):
        account = raw.iloc[i, account_col]
        # Summary rows in this export may be in the cell immediately left of Account.
        if pd.isna(account):
            account = raw.iloc[i, 0]
        if pd.isna(account):
            continue
        account = str(account).strip()
        if account.casefold() in headers_to_section:
            section = headers_to_section[account.casefold()]
            continue
        # A section's total row closes it; later rows (e.g. profit lines) belong to no section.
        if section is not None and totals_to_section.get(account.casefold()) == section:
            section = None
        sections[account] = section
        row_of.setdefault(account, i + 1)
        row, blanks = {"account": account}, []
        for j, month in date_cols:
            value, problem = to_number(raw.iloc[i, j])
            row[month] = np.nan if value is None else value
            ref = (f"{sheet}!{get_column_letter(j + 1)}{i + 1}", account, f"{month:%b %Y}")
            if problem == "blank":
                blanks.append(ref)
            elif problem:
                bad_cells.append((*ref, problem))
        if len(blanks) < len(date_cols):  # a row blank in every month is a block header, not missing data
            blank_cells += blanks
        rows.append(row)
    data = pd.DataFrame(rows).set_index("account")
    data = data.loc[:, sorted([m for _, m in date_cols])]
    data.columns.name = "month"
    data.attrs.update(sections=sections, sheet=sheet, row_of=row_of, bad_cells=bad_cells, blank_cells=blank_cells,
                      col_of={m: get_column_letter(j + 1) for j, m in date_cols})
    return data

LONG_ROLES = ("account", "month", "amount", "section")  # section is optional (a Balance Sheet has none)


def long_header(headers, columns, sheet, header_row):
    """{role: column index} for a long-format header row. Raises ValueError naming any configured column that is
    missing and any column that is not configured (an unknown column is a STOP, not something to skip silently)."""
    names = [None if h is None or (isinstance(h, float) and np.isnan(h)) else str(h).strip() for h in headers]
    unknown_roles = sorted(set(columns) - set(LONG_ROLES))
    if unknown_roles:
        raise ValueError(f"layout.columns has unknown role(s) {unknown_roles}; use {list(LONG_ROLES)}.")
    missing = [f"{columns[r]!r} ({r})" for r in ("account", "month", "amount") if columns.get(r) not in names]
    if missing:
        raise ValueError(f"{sheet}: column {', '.join(missing)} not found in header row {header_row}; columns present: "
                         f"{[n for n in names if n]}.")
    expected = {v for v in columns.values()}
    unknown = [(n, f"{get_column_letter(j + 1)}{header_row}") for j, n in enumerate(names) if n and n not in expected]
    if unknown:
        raise ValueError(f"{sheet}: unknown column {unknown[0][0]!r} at {unknown[0][1]}"
                         + (f" (and {len(unknown) - 1} more)" if len(unknown) > 1 else "")
                         + f"; the long layout expects only {sorted(expected)}. Rename it or add it to layout.columns.")
    return {r: names.index(columns[r]) for r in LONG_ROLES if columns.get(r) in names}


def parse_long_income_statement(path, layout):
    """Long format: one row per (account, month) with the columns named in layout['columns']
    (account, month, amount and optionally section). Returns the same frame and attrs as the wide parser.

    STOP (ValueError): a configured column missing, an unknown column, a month that cannot be read, an unknown section
    label, an account given two sections, or the same (account, month) twice. WARN (blank_cells): an account with no
    row for a month that other accounts have, kept as missing (not zero)."""
    sheet, columns, fmt = layout["sheet"], layout["columns"], layout["month_format"]
    raw = pd.read_excel(path, sheet_name=sheet, header=None, keep_default_na=False)
    raw = raw.mask(raw.eq(""))
    header_row = next((i for i in range(min(15, len(raw))) if columns["account"] in raw.iloc[i].astype(str).str.strip().tolist()), None)
    if header_row is None:
        raise ValueError(f"Could not find the '{columns['account']}' header row in {sheet}.")
    col = long_header(raw.iloc[header_row].tolist(), columns, sheet, header_row + 1)
    to_section = {h.casefold(): sid for sid, (h, _) in layout.get("sections", {}).items()}
    amount_letter = get_column_letter(col["amount"] + 1)
    values, sections, row_of, cell_of, seen, bad_cells, order = {}, {}, {}, {}, {}, [], []
    for i in range(header_row + 1, len(raw)):
        account = raw.iloc[i, col["account"]]
        if pd.isna(account):
            continue
        account, excel_row = str(account).strip(), i + 1
        m = raw.iloc[i, col["month"]]
        month = (pd.Timestamp(m) if isinstance(m, (pd.Timestamp, np.datetime64)) or hasattr(m, "year")
                 else pd.to_datetime(str(m).strip(), format=fmt, errors="coerce"))
        if pd.isna(month):
            raise ValueError(f"{sheet}!{get_column_letter(col['month'] + 1)}{excel_row}: month {m!r} does not match format {fmt!r}.")
        month = month.to_period("M").to_timestamp()
        label = raw.iloc[i, col["section"]] if "section" in col else None
        section = None
        if label is not None and not pd.isna(label) and str(label).strip():
            section = to_section.get(str(label).strip().casefold())
            if section is None:
                raise ValueError(f"{sheet}!{get_column_letter(col['section'] + 1)}{excel_row}: unknown section {str(label).strip()!r}; "
                                 f"expected one of {[h for h, _ in layout.get('sections', {}).values()]} or blank.")
        if account in sections and sections[account] != section:
            raise ValueError(f"{sheet}: account {account!r} is in section {sections[account]!r} at row {row_of[account]} "
                             f"but {section!r} at row {excel_row}.")
        if (account, month) in seen:
            raise ValueError(f"{sheet}: {account!r} {month:%b %Y} appears twice, in rows {seen[(account, month)]} and {excel_row}. "
                             "Remove the duplicate row.")
        seen[(account, month)] = excel_row
        if account not in sections:
            order.append(account)
            sections[account], row_of[account] = section, excel_row
        ref = f"{sheet}!{amount_letter}{excel_row}"
        cell_of[(account, month)] = ref
        value, problem = to_number(raw.iloc[i, col["amount"]])
        if problem and problem != "blank":
            bad_cells.append((ref, account, f"{month:%b %Y}", problem))
        values.setdefault(account, {})[month] = np.nan if value is None else value
    months = sorted({m for _, m in seen})
    if len(months) < 2:
        raise ValueError(f"Expected at least two months in {sheet}.")
    blank_cells = []
    for account in order:
        blanks = [(cell_of.get((account, m), f"{sheet} (no row)"), account, f"{m:%b %Y}") for m in months
                  if pd.isna(values[account].get(m, np.nan))]
        if len(blanks) < len(months):  # an account with no amount in any month is a block header, as in the wide parser
            blank_cells += blanks
    data = pd.DataFrame([[values[a].get(m, np.nan) for m in months] for a in order], index=pd.Index(order, name="account"),
                        columns=pd.Index(months, name="month"))
    data.attrs.update(sections=sections, sheet=sheet, row_of=row_of, col_of={}, cell_of=cell_of, bad_cells=bad_cells,
                      blank_cells=blank_cells, header_row=header_row + 1, account_col=col["account"], source="long")
    return data


def build_monthly_summary(account_month, totals=None):
    def find_row(name):
        matches = account_month.loc[account_month.index.str.casefold() == name.casefold()]
        return matches.iloc[0] if not matches.empty else None
    mapping = totals or ABC_TOTALS
    rows = {}
    for metric, account in mapping.items():
        row = find_row(account)
        if row is not None:
            rows[metric] = row
    out = pd.DataFrame(rows)
    out.index = pd.to_datetime(out.index)
    out.index.name = "month"
    out = out.sort_index()
    if "revenue" in out:
        out["revenue_mom_change"] = out["revenue"].diff()
        out["revenue_mom_pct"] = out["revenue"].pct_change().where(out["revenue"].shift(1) != 0)
    if {"gross_profit", "revenue"}.issubset(out.columns):
        out["gross_margin_pct"] = (out["gross_profit"] / out["revenue"]).where(out["revenue"] != 0)
    if {"operating_income", "revenue"}.issubset(out.columns):
        out["operating_margin_pct"] = (out["operating_income"] / out["revenue"]).where(out["revenue"] != 0)
    if {"net_income", "revenue"}.issubset(out.columns):
        out["net_margin_pct"] = (out["net_income"] / out["revenue"]).where(out["revenue"] != 0)
    # A TTM total requires 12 consecutive calendar months, not merely 12 columns.
    months = out.index.to_series()
    consecutive = (months.dt.year * 12 + months.dt.month).diff().eq(1)
    valid_window = consecutive.rolling(11, min_periods=11).sum().eq(11)
    for metric in mapping:
        if metric in out.columns:
            out[f"{metric}_ttm"] = out[metric].rolling(12, min_periods=12).sum().where(valid_window)
    return out.reset_index()

def build_expense_category_trends(account_month, subtotal_rows=ABC_SUBTOTAL_ROWS):
    # Detail-level expense lines only; exclude subtotal/total rows to avoid double counting.
    exclude = {r.casefold() for r in subtotal_rows} | {
        "total income", "total cost of goods sold", "gross profit",
        "total operating expenses", "operating income", "net income",
        "income", "cost of goods sold", "operating expenses",
    }
    # Keep operating expense accounts only, using the section boundaries recorded by the parser
    # (the Operating Expenses header row through its Total row).
    sections = account_month.attrs.get("sections")
    if sections is None:
        raise ValueError("account_month has no section map; build it with parse_wide_income_statement.")
    names = [
        name for name in account_month.index
        if sections.get(name) == "operating expenses" and str(name).strip().casefold() not in exclude
    ]
    expense = account_month.loc[names]
    expense.index.name = "expense_category"
    out = expense.reset_index().melt(id_vars="expense_category", var_name="month", value_name="amount")
    out = out.sort_values(["expense_category", "month"])
    out["mom_change"] = out.groupby("expense_category")["amount"].diff()
    # Divide by |prior| so the sign follows the direction of change (a credit reversing to zero is +).
    prior = out.groupby("expense_category")["amount"].shift(1)
    out["mom_pct"] = (out["mom_change"] / prior.abs()).where(prior != 0)
    return out.sort_values(["month", "expense_category"]).reset_index(drop=True)

def build_category_rollup(expense_trends, account_to_category):
    """Roll detail OPEX accounts up to reporting categories. Unmapped accounts go to 'Unmapped', never dropped."""
    x = expense_trends.assign(category=expense_trends["expense_category"].map(account_to_category).fillna("Unmapped"))
    out = x.groupby(["category", "month"], as_index=False)["amount"].sum(min_count=1)
    out = out.sort_values(["category", "month"])
    out["mom_change"] = out.groupby("category")["amount"].diff()
    prior = out.groupby("category")["amount"].shift(1)
    out["mom_pct"] = (out["mom_change"] / prior.abs()).where(prior != 0)
    out["share_of_opex"] = out["amount"] / out.groupby("month")["amount"].transform("sum")
    return out.sort_values(["month", "category"]).reset_index(drop=True)

def add_fiscal_year(monthly, start_month=1):
    """Label each month with its fiscal year and add fiscal-year-to-date totals."""
    out = monthly.copy()
    months = pd.to_datetime(out["month"])
    first_year = months.dt.year - (months.dt.month < start_month).astype(int)
    if start_month == 1:
        out["fiscal_year"] = "FY" + first_year.astype(str)
    else:
        out["fiscal_year"] = "FY" + first_year.astype(str) + "-" + ((first_year + 1) % 100).astype(str).str.zfill(2)
    for col in ["revenue", "gross_profit", "operating_expenses", "net_income"]:
        if col in out.columns:
            out[f"{col}_fytd"] = out.groupby("fiscal_year")[col].cumsum()
    return out

def margin_drop_flags(monthly, threshold_pp):
    """Months whose gross margin fell by more than `threshold_pp` percentage points versus the prior month."""
    m = (monthly if "month" in monthly.columns else monthly.reset_index()).sort_values("month").reset_index(drop=True)
    adjacent = m["month"].diff().dt.days.between(28, 31)  # no change is measured across a missing month
    change_pp = (m["gross_margin_pct"].diff() * 100).where(adjacent)
    return [{"month": f"{r.month:%Y-%m}", "gross_margin_pct": float(r.gross_margin_pct), "change_pp": float(c)}
            for r, c in zip(m.itertuples(), change_pp) if pd.notna(c) and c < -threshold_pp]


def find_one_off_items(account_month, min_abs=5000.0):
    """Detail accounts that are non-zero in exactly one month with |amount| >= min_abs."""
    sections = account_month.attrs.get("sections", {})
    detail = [a for a in account_month.index if sections.get(a) and not a.casefold().startswith("total ")]
    rows = []
    for account in detail:
        values = account_month.loc[account]
        if values.isna().all():  # block header rows inside a section carry no values
            continue
        nonzero = values[values.fillna(0) != 0]
        if len(nonzero) == 1 and abs(nonzero.iloc[0]) >= min_abs:
            rows.append({"account": account, "section": sections[account], "month": nonzero.index[0], "amount": float(nonzero.iloc[0])})
    return pd.DataFrame(rows, columns=["account", "section", "month", "amount"]).sort_values(["month", "account"]).reset_index(drop=True)

def cash_position(balance_sheet, cash_row=ABC_CASH_ROW, windows=(1, 3, 6)):
    """Latest cash balance and runway = cash / average monthly decline in the cash balance over each window.

    Burn comes from month-end Balance Sheet cash, not from net income. Runway is None when the window's
    cash did not decline (no burn) or the history is too short.
    """
    cash = balance_sheet.loc[cash_row].dropna().sort_index()
    latest = cash.index[-1]
    out = {"month": latest, "cash": float(cash.iloc[-1]), "prior_cash": float(cash.iloc[-2]), "burn": {}, "runway_months": {}}
    for n in windows:
        if len(cash) <= n:
            out["burn"][n] = out["runway_months"][n] = None
            continue
        burn = (cash.iloc[-1 - n] - cash.iloc[-1]) / n
        out["burn"][n] = float(burn)
        out["runway_months"][n] = float(cash.iloc[-1] / burn) if burn > 0 else None
    return out

def top_movements(account_month, month, n=3):
    """Latest-month detail rows (sectioned, not 'Total ...') ranked by absolute MoM $ change, as in the review packet."""
    months = sorted(account_month.columns)
    prior = months[months.index(month) - 1]
    sections = account_month.attrs.get("sections", {})
    rows = []
    for account in account_month.index:
        if not sections.get(account) or account.casefold().startswith("total "):
            continue
        cur, prev = account_month.at[account, month], account_month.at[account, prior]
        if pd.notna(cur) and pd.notna(prev):
            rows.append((account, sections[account], float(cur), float(prev), float(cur - prev)))
    return sorted(rows, key=lambda r: abs(r[4]), reverse=True)[:n]

def generate_commentary(monthly, account_month=None, cash=None, runway_window=3):
    m = monthly.sort_values("month")
    last = m.iloc[-1]
    prev = m.iloc[-2]
    notes = []
    for label, col in [("Revenue", "revenue"), ("Gross profit", "gross_profit"), ("Operating expenses", "operating_expenses"), ("Net income", "net_income")]:
        if col not in m.columns:
            continue
        cur, prior = last[col], prev[col]
        if pd.notna(cur) and pd.notna(prior):
            change = cur - prior
            # Divide by |prior| so the sign follows the direction of change (e.g. a shrinking loss is +).
            pct = (change / abs(prior)) if prior != 0 else np.nan
            pct_text = f" ({pct:+.1%})" if pd.notna(pct) else " (percentage change unavailable because prior value is zero)"
            notes.append(f"{label}: {cur:,.2f} in {pd.Timestamp(last['month']).strftime('%b %Y')}; month-over-month change {change:+,.2f}{pct_text}.")
    if "gross_margin_pct" in m.columns:
        notes.append(f"Latest gross margin: {last['gross_margin_pct']:.1%}.")
    if "operating_margin_pct" in m.columns:
        notes.append(f"Latest operating margin: {last['operating_margin_pct']:.1%}.")
    if "net_margin_pct" in m.columns:
        notes.append(f"Latest net margin: {last['net_margin_pct']:.1%}.")
    month = pd.Timestamp(last["month"])
    if account_month is not None and month in account_month.columns:
        for i, (account, section, cur, prev, change) in enumerate(top_movements(account_month, month), 1):
            pct_text = f" ({change / abs(prev):+.1%})" if prev else ""
            notes.append(f"Top movement {i} ({section}): {account} {cur:,.2f} in {month:%b %Y}; change {change:+,.2f}{pct_text}.")
    if cash is not None:
        cash_month = pd.Timestamp(cash["month"])
        burn, runway = cash["burn"].get(runway_window), cash["runway_months"].get(runway_window)
        line = f"Cash: {cash['cash']:,.2f} at {cash_month:%b %Y} month-end; change {cash['cash'] - cash['prior_cash']:+,.2f}."
        if runway is not None:
            line += (f" Runway: {runway:.1f} months at the {runway_window}-month average decline in Balance Sheet cash"
                     f" ({burn:,.2f} per month); based on past balances only, not a forecast.")
        else:
            line += f" Runway: not calculable because cash did not decline over the last {runway_window} months."
        notes.append(line)
    notes.append("Commentary describes observed changes only; it does not infer causes from the financial statements.")
    return notes

def analyze_wide_workbook(path, output_path):
    account_month = parse_wide_income_statement(path)
    monthly = build_monthly_summary(account_month)
    categories = build_expense_category_trends(account_month)
    commentary = pd.DataFrame({"commentary": generate_commentary(monthly)})
    # Pivot account-level monthly values into a readable table
    account_table = account_month.copy()
    account_table.index.name = "account"
    account_table = account_table.reset_index()
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        monthly.to_excel(writer, sheet_name="Monthly Trends", index=False)
        categories.to_excel(writer, sheet_name="Expense Category Trends", index=False)
        account_table.to_excel(writer, sheet_name="Account Values", index=False)
        commentary.to_excel(writer, sheet_name="Commentary", index=False)
    return monthly, categories, Path(output_path)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Analyze the ABC Inc wide-format financial workbook.")
    parser.add_argument("workbook", help="Path to ABC Inc Excel workbook")
    parser.add_argument("--output", default="ABC_Inc_Financial_Analysis.xlsx")
    args = parser.parse_args()
    analyze_wide_workbook(args.workbook, args.output)
    print(f"Analysis written to: {Path(args.output).resolve()}")
