"""Deterministic monthly financial analysis helpers for the assessment scaffold."""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

REQUIRED = {"month", "revenue"}

def normalize_monthly(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize one row per month, preserving optional measures."""
    out = df.copy()
    missing = REQUIRED - set(out.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    out["month"] = pd.to_datetime(out["month"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    if out["month"].isna().any():
        raise ValueError("Some month values could not be parsed as dates.")
    out = out.sort_values("month").reset_index(drop=True)
    if out["month"].duplicated().any():
        raise ValueError("Expected one row per month. Aggregate duplicate months before analysis.")
    for col in ["revenue", "gross_profit", "operating_expenses", "net_income"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    if out["revenue"].isna().any():
        raise ValueError("Revenue contains blank or non-numeric values.")
    out["revenue_mom_change"] = out["revenue"].diff()
    out["revenue_mom_pct"] = out["revenue"].pct_change().where(out["revenue"].shift(1) != 0)
    if "gross_profit" in out.columns:
        out["gross_margin_pct"] = (out["gross_profit"] / out["revenue"]).where(out["revenue"] != 0)
        out["gross_profit_mom_change"] = out["gross_profit"].diff()
    if "operating_expenses" in out.columns:
        out["operating_expenses_mom_change"] = out["operating_expenses"].diff()
        out["operating_expenses_mom_pct"] = (
            out["operating_expenses"].pct_change().where(out["operating_expenses"].shift(1) != 0)
        )
    if "net_income" in out.columns:
        out["net_margin_pct"] = (out["net_income"] / out["revenue"]).where(out["revenue"] != 0)
    # A TTM total requires 12 consecutive calendar months, not merely 12 rows.
    consecutive = out["month"].diff().dt.days.between(27, 32).fillna(False)
    valid_window = consecutive.rolling(11, min_periods=11).sum().eq(11)
    for col in ["revenue", "gross_profit", "operating_expenses", "net_income"]:
        if col in out.columns:
            rolling = out[col].rolling(12, min_periods=12).sum()
            out[f"{col}_ttm"] = rolling.where(valid_window)
    return out

def category_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Summarize expenses by category when long-form category data is provided."""
    required = {"month", "expense_category", "expense_amount"}
    if not required.issubset(df.columns):
        return pd.DataFrame(columns=["month", "expense_category", "expense_amount", "expense_mom_change", "expense_mom_pct"])
    x = df.copy()
    x["month"] = pd.to_datetime(x["month"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    x["expense_amount"] = pd.to_numeric(x["expense_amount"], errors="coerce")
    monthly = x.groupby(["month", "expense_category"], as_index=False)["expense_amount"].sum()
    monthly = monthly.sort_values(["expense_category", "month"])
    monthly["expense_mom_change"] = monthly.groupby("expense_category")["expense_amount"].diff()
    monthly["expense_mom_pct"] = monthly.groupby("expense_category")["expense_amount"].pct_change()
    return monthly.sort_values(["month", "expense_category"]).reset_index(drop=True)

def make_commentary(monthly: pd.DataFrame) -> list[str]:
    """Produce transparent, rule-based observations; no unsupported causal claims."""
    notes = []
    if monthly.empty:
        return ["No monthly data available."]
    last = monthly.iloc[-1]
    if pd.notna(last.get("revenue_mom_pct")):
        direction = "increased" if last["revenue_mom_pct"] > 0 else "decreased" if last["revenue_mom_pct"] < 0 else "was unchanged"
        notes.append(f"Revenue {direction} by {last['revenue_mom_pct']:.1%} versus the previous available month.")
    else:
        notes.append("Revenue month-over-month percentage change is unavailable for the latest row (first month or prior revenue is zero/missing).")
    if "gross_margin_pct" in monthly.columns and pd.notna(last.get("gross_margin_pct")):
        notes.append(f"Latest gross margin is {last['gross_margin_pct']:.1%}.")
    if "net_margin_pct" in monthly.columns and pd.notna(last.get("net_margin_pct")):
        notes.append(f"Latest net margin is {last['net_margin_pct']:.1%}.")
    if len(monthly) < 12:
        notes.append("TTM totals are not yet available because fewer than 12 monthly observations were supplied.")
    elif "revenue_ttm" in monthly.columns and pd.isna(last.get("revenue_ttm")):
        notes.append("TTM totals are unavailable for the latest period because the latest 12 rows do not represent 12 consecutive calendar months or contain incomplete values.")
    else:
        notes.append("TTM totals are calculated from the latest 12 consecutive calendar months.")
    notes.append("These are descriptive observations; the data alone does not establish the cause of a change.")
    return notes

def analyze_file(path: str | Path, sheet_name: str | int = 0, output_path: str | Path = "financial_analysis_output.xlsx") -> Path:
    """Read a normalized Excel worksheet and write analysis tabs to an output workbook."""
    df = pd.read_excel(path, sheet_name=sheet_name)
    monthly = normalize_monthly(df)
    categories = category_summary(df)
    comments = pd.DataFrame({"commentary": make_commentary(monthly)})
    output_path = Path(output_path)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        monthly.to_excel(writer, sheet_name="Monthly Analysis", index=False)
        categories.to_excel(writer, sheet_name="Expense Categories", index=False)
        comments.to_excel(writer, sheet_name="Commentary", index=False)
    return output_path

def main():
    parser = argparse.ArgumentParser(description="Analyze a normalized monthly financial workbook.")
    parser.add_argument("workbook", help="Path to input Excel workbook")
    parser.add_argument("--sheet", default=0, help="Worksheet name or index (default: first sheet)")
    parser.add_argument("--output", default="financial_analysis_output.xlsx")
    args = parser.parse_args()
    sheet = int(args.sheet) if str(args.sheet).isdigit() else args.sheet
    output = analyze_file(args.workbook, sheet, args.output)
    print(f"Analysis written to: {output.resolve()}")

if __name__ == "__main__":
    main()
