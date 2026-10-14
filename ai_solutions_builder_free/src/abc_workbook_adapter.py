"""Adapter for wide-format monthly income statements (one column per month).

Defaults match the ABC Inc workbook. Other clients pass their labels from clients/<client>/config.yaml
(see src/run_client.py), so a new client needs a config file, not a code change.
"""
from pathlib import Path
import pandas as pd
import numpy as np

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

def parse_wide_income_statement(path, layout=None):
    layout = layout or ABC_LAYOUT
    sheet, header_label = layout["sheet"], layout["header_label"]
    raw = pd.read_excel(path, sheet_name=sheet, header=None)
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
    headers_to_section = {h.casefold(): sid for sid, (h, _) in layout["sections"].items()}
    totals_to_section = {t.casefold(): sid for sid, (_, t) in layout["sections"].items()}
    rows = []
    sections = {}
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
        row = {"account": account}
        for j, month in date_cols:
            row[month] = pd.to_numeric(raw.iloc[i, j], errors="coerce")
        rows.append(row)
    data = pd.DataFrame(rows).set_index("account")
    data = data.loc[:, sorted([m for _, m in date_cols])]
    data.columns.name = "month"
    data.attrs["sections"] = sections
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
