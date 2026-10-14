"""Run deterministic golden cases for the monthly financial-analysis engine."""
from __future__ import annotations
import json
import math
import re
import sys
from pathlib import Path
import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from financial_analysis import normalize_monthly, category_summary, make_commentary  # noqa: E402
import abc_workbook_adapter as abc  # noqa: E402

CASES = ROOT / "03_evals" / "golden_cases.json"
WORKBOOK = ROOT / "data" / "ABC Inc - Financial Statements.xlsx"
CENT = 0.005
_abc = {}


def abc_outputs():
    """Adapter outputs for the real workbook, read-only, computed once per run."""
    if not _abc:
        am = abc.parse_wide_income_statement(WORKBOOK)
        _abc.update(account_month=am, monthly=abc.build_monthly_summary(am).set_index("month"),
                    categories=abc.build_expense_category_trends(am),
                    balance_sheet=abc.parse_wide_income_statement(WORKBOOK, abc.ABC_BS_LAYOUT))
    return _abc


_cells = {}


def source_cells():
    """Cached Income Statement cell values, read-only and in memory: {(row, col letter): value}."""
    if not _cells:
        ws = openpyxl.load_workbook(WORKBOOK, data_only=True, read_only=True)["Income Statement"]
        for r in ws.iter_rows(min_row=1, max_row=110, max_col=20):
            for c in r:
                if c.value is not None:
                    _cells[(c.row, c.column_letter)] = c.value
    return _cells


def perturbed_cells(case):
    """Copy of the source cells with the case's perturbation applied; refuses if a recorded original is wrong."""
    cells = dict(source_cells())
    for ch in case["perturbation"]["cells_changed"]:
        m = re.fullmatch(r"([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?", ch["cell"])
        c1, r1, c2, r2 = m.group(1), int(m.group(2)), m.group(3) or m.group(1), int(m.group(4) or m.group(2))
        if c1 == c2 and r1 == r2:
            if cells.get((r1, c1)) != ch["original"]:
                raise ValueError(f"{ch['cell']}: recorded original {ch['original']!r} != workbook {cells.get((r1, c1))!r}")
        for col in [chr(x) for x in range(ord(c1), ord(c2) + 1)]:
            for row in range(r1, r2 + 1):
                if ch["new"] is None:
                    cells.pop((row, col), None)
                else:
                    cells[(row, col)] = ch["new"]
    return cells


def real_frame(case):
    """Month/value frame for the engine from perturbed workbook cells."""
    cells, inp = perturbed_cells(case), case["input"]
    cols = inp["columns"]
    if cols == "all":
        cols = [chr(x) for x in range(ord("C"), ord("T") + 1) if (5, chr(x)) in cells]
    df = pd.DataFrame({"month": [cells[(5, c)] for c in cols]})
    df["month"] = pd.to_datetime(df["month"].astype(str), format="mixed")
    def label(row):
        return cells.get((row, "A")) or cells.get((row, "B"))
    if "revenue_row" in inp and label(inp["revenue_row"]) == "Total Income":
        df["revenue"] = [cells[(inp["revenue_row"], c)] for c in cols]
    if "gross_profit_row" in inp:
        df["gross_profit"] = [cells[(inp["gross_profit_row"], c)] for c in cols]
    return df, cells, cols


def close(actual, expected, tol=CENT):
    return actual is not None and not pd.isna(actual) and abs(float(actual) - float(expected)) <= tol


def run_abc_case(typ, data, expected):
    o = abc_outputs()
    am, monthly, cats = o["account_month"], o["monthly"], o["categories"]
    if typ == "abc_seasonal_peak":
        errors = []
        for account, by_month in expected["values"].items():
            row = am.loc[account]
            for year, month in expected["peak_month_by_year"].items():
                year_row = row[pd.DatetimeIndex(row.index).year == int(year)]
                if year_row.idxmax() != pd.Timestamp(month):
                    errors.append(f"{account} {year} peak={year_row.idxmax():%Y-%m}")
            errors += [f"{account} {m}={row[pd.Timestamp(m)]}" for m, v in by_month.items() if not close(row[pd.Timestamp(m)], v)]
        return not errors, "; ".join(errors) or "February peak in 2025 and 2026"
    if typ == "abc_one_off":
        found = abc.find_one_off_items(am, data["min_abs"])
        got = {(r.account, r.month.strftime("%Y-%m-%d")): r.amount for r in found.itertuples()}
        want = {(i["account"], i["month"]): i["amount"] for i in expected["one_off_items"]}
        ok = got.keys() == want.keys() and all(close(got[k], want[k]) for k in want)
        event = pd.Timestamp(expected["event_month"])
        positive_ni = list(monthly.index[monthly["net_income"] > 0])
        ok = ok and positive_ni == [event]
        ok = ok and all(close(monthly.at[event, k], v) for k, v in expected["event_month_totals"].items())
        # Removing an OPEX item from the month moves net income by +amount (expenses reduce NI).
        adjusted = monthly.at[event, "net_income"] + sum(
            v for (a, m), v in got.items() if pd.Timestamp(m) == event and found.set_index("account").at[a, "section"] == "operating expenses")
        ok = ok and close(adjusted, expected["net_income_excluding_one_offs"])
        return ok, f"one-offs={sorted(got)}; positive NI months={[f'{m:%Y-%m}' for m in positive_ni]}; NI ex one-offs={adjusted:,.2f}"
    if typ == "abc_first_ttm":
        first = pd.Timestamp(expected["first_valid_month"])
        valid = monthly.index[monthly["revenue_ttm"].notna()]
        ok = len(valid) > 0 and valid[0] == first and pd.isna(monthly.at[pd.Timestamp(expected["prior_month_ttm_is_null"]), "revenue_ttm"])
        # Every month before the first valid one must be unavailable for every TTM metric, not just the month before.
        earlier = monthly.loc[monthly.index < first, [f"{k}_ttm" for k in expected["ttm"]]]
        ok = ok and earlier.isna().all().all()
        ok = ok and all(close(monthly.at[first, f"{k}_ttm"], v) for k, v in expected["ttm"].items())
        return ok, f"first valid TTM={valid[0]:%Y-%m} revenue_ttm={monthly.at[first, 'revenue_ttm']:,.2f}; {len(earlier)} earlier months all null={earlier.isna().all().all()}"
    if typ == "abc_line_item_step":
        row, month = am.loc[data["account"]], pd.Timestamp(data["month"])
        prior = row[month - pd.DateOffset(months=1)]
        held = row[(row.index >= month) & (row.index <= pd.Timestamp(expected["held_through"]))]
        ok = (close(prior, expected["prior_value"]) and close(row[month], expected["value"])
              and close(row[month] - prior, expected["mom_change"]) and close((row[month] - prior) / abs(prior), expected["mom_pct"], 1e-6)
              and all(close(v, expected["value"]) for v in held))
        return ok, f"{prior:,.2f} -> {row[month]:,.2f} ({row[month] - prior:+,.2f}); held {len(held)} months"
    if typ == "abc_line_item_value":
        row = am.loc[data["account"]]
        errors = [f"{m}={row[pd.Timestamp(m)]}" for m, v in expected["values"].items() if not close(row[pd.Timestamp(m)], v)]
        may = cats[(cats["expense_category"] == data["account"]) & (cats["month"] == pd.Timestamp("2026-05-01"))].iloc[0]
        if expected["mom_pct_may_2026"] is None and not pd.isna(may["mom_pct"]):
            errors.append(f"May 2026 mom_pct={may['mom_pct']} expected null")
        return not errors, "; ".join(errors) or f"values match; May 2026 mom_pct={may['mom_pct']}"
    if typ == "abc_cash_runway":
        pos = abc.cash_position(o["balance_sheet"], data["cash_row"], windows=tuple(int(n) for n in expected["burn"]))
        ok = (pos["month"] == pd.Timestamp(expected["month"]) and close(pos["cash"], expected["cash"])
              and close(pos["prior_cash"], expected["prior_cash"])
              and all(close(pos["burn"][int(n)], v) for n, v in expected["burn"].items())
              and all(close(pos["runway_months"][int(n)], v, 1e-6) for n, v in expected["runway_months"].items()))
        primary = int(data["primary_window_months"])
        return ok, f"cash={pos['cash']:,.2f}; {primary}m burn={pos['burn'][primary]:,.2f}; runway={pos['runway_months'][primary]:.2f} months"
    if typ == "abc_opex_spike":
        one_offs = set(abc.find_one_off_items(am, data["exclude_one_offs_min_abs"])["account"])
        details = []
        # A spike is an increase to a positive expense; a credit reversing to zero is not a spike.
        spikes = cats[cats["amount"] > 0]
        for key, pool in [("largest_overall", spikes), ("largest_recurring", spikes[~spikes["expense_category"].isin(one_offs)])]:
            top = pool.loc[pool["mom_change"].idxmax()]
            exp = expected[key]
            ok = (top["expense_category"] == exp["account"] and top["month"] == pd.Timestamp(exp["month"])
                  and close(top["amount"], exp["amount"]) and close(top["mom_change"], exp["mom_change"])
                  and (pd.isna(top["mom_pct"]) if exp["mom_pct"] is None else close(top["mom_pct"], exp["mom_pct"], 1e-6)))
            details.append((ok, f"{key}={top['expense_category']} {top['month']:%Y-%m} +{top['mom_change']:,.2f} pct={top['mom_pct']}"))
        return all(d[0] for d in details), "; ".join(d[1] for d in details)
    if typ == "abc_latest_summary":
        month = pd.Timestamp(data["month"])
        errors = []
        for metric, fields in expected.items():
            for field, v in fields.items():
                col = {"value": metric, "ttm": f"{metric}_ttm", "mom_change": f"{metric}_mom_change",
                       "mom_pct": f"{metric}_mom_pct", "margin": {"gross_profit": "gross_margin_pct",
                       "operating_income": "operating_margin_pct", "net_income": "net_margin_pct"}.get(metric)}[field]
                tol = 1e-6 if field in {"mom_pct", "margin"} else CENT
                actual = monthly.at[month, col] if col in monthly.columns else None
                if not close(actual, v, tol):
                    errors.append(f"{metric}.{field}={actual} expected {v}")
        return not errors, "; ".join(errors) or "all summary fields match"
    return False, f"Unknown case type: {typ}"


def approx(actual, expected, tol=1e-6):
    return actual is not None and not pd.isna(actual) and math.isclose(float(actual), float(expected), abs_tol=tol, rel_tol=tol)


def run_real_case(case):
    """G01-G08 and G14: the same engine rules, fed from (perturbed) real workbook cells."""
    typ, expected = case["type"], case["expected"]
    df, cells, cols = real_frame(case)
    if typ in {"revenue_mom", "zero_prior_revenue"}:
        out = normalize_monthly(df)
        change, pct = out.iloc[-1]["revenue_mom_change"], out.iloc[-1]["revenue_mom_pct"]
        ok = close(change, expected["absolute_change"])
        ok = ok and (pd.isna(pct) if expected["percentage_change"] is None else approx(pct, expected["percentage_change"]))
        return ok, f"change={change}, pct={pct}"
    if typ == "month_labels":
        out = normalize_monthly(df)
        got = [f"{m:%Y-%m-%d}" for m in out["month"]]
        ok = got == expected["months"] and all(close(a, b) for a, b in zip(out["revenue"], expected["revenue"]))
        return ok, f"months={got}, revenue={out['revenue'].tolist()}"
    if typ == "gross_margin":
        actual = normalize_monthly(df).iloc[0]["gross_margin_pct"]
        return approx(actual, expected["gross_margin"]), f"gross_margin={actual}"
    if typ == "ttm":
        out = normalize_monthly(df)
        before, after = out.iloc[10]["revenue_ttm"], out.iloc[11]["revenue_ttm"]
        return pd.isna(before) and close(after, expected["ttm_after_12"]), f"ttm_after_11={before}, ttm_after_12={after}"
    if typ in {"duplicate_month", "missing_revenue"}:
        try:
            normalize_monthly(df)
        except ValueError as exc:
            return expected["raises"] in str(exc), str(exc)
        return False, "No validation error was raised"
    if typ == "expense_category":
        amounts = [cells[(case["input"]["category_row"], c)] for c in cols]
        long = pd.DataFrame({"month": df["month"], "expense_category": expected["category"], "expense_amount": amounts})
        last = category_summary(long).iloc[-1]
        ok = close(last["expense_mom_change"], expected["absolute_change"]) and approx(last["expense_mom_pct"], expected["percentage_change"])
        return ok, f"change={last['expense_mom_change']}, pct={last['expense_mom_pct']}"
    if typ == "short_history_commentary":
        out = normalize_monthly(df)
        text = " ".join(make_commentary(out))
        return len(out) == expected["months_remaining"] and expected["commentary_contains"].lower() in text.lower(), f"{len(out)} months; {text}"
    return False, f"Unknown case type: {typ}"


def run_case(case):
    typ, data, expected = case["type"], case["input"], case["expected"]
    if isinstance(case.get("source"), str) and case["source"].startswith("workbook"):
        return run_real_case(case)
    if typ.startswith("abc_"):
        return run_abc_case(typ, data, expected)
    if typ in {"revenue_mom", "zero_prior_revenue"}:
        df = pd.DataFrame({"month": data["months"], "revenue": data["revenue"]})
        out = normalize_monthly(df)
        actual_change = out.iloc[-1]["revenue_mom_change"]
        actual_pct = out.iloc[-1]["revenue_mom_pct"]
        ok = approx(actual_change, expected["absolute_change"])
        if expected["percentage_change"] is None:
            ok = ok and pd.isna(actual_pct)
        else:
            ok = ok and approx(actual_pct, expected["percentage_change"])
        return ok, f"change={actual_change}, pct={actual_pct}"
    if typ == "month_labels":
        out = normalize_monthly(pd.DataFrame({"month": data["months"], "revenue": data["revenue"]}))
        got = [f"{m:%Y-%m-%d}" for m in out["month"]]
        ok = got == expected["months"] and out["revenue"].tolist() == expected["revenue"]
        return ok, f"months={got}, revenue={out['revenue'].tolist()}"
    if typ == "gross_margin":
        out = normalize_monthly(pd.DataFrame([data]))
        actual = out.iloc[0]["gross_margin_pct"]
        return approx(actual, expected["gross_margin"]), f"gross_margin={actual}"
    if typ == "ttm":
        n = data["months_after"]
        months = pd.date_range(data["start_month"], periods=n, freq="MS")
        out = normalize_monthly(pd.DataFrame({"month": months, "revenue": [data["revenue_each_month"]] * n}))
        before = out.iloc[10]["revenue_ttm"]
        after = out.iloc[11]["revenue_ttm"]
        ok = pd.isna(before) and approx(after, expected["ttm_after_12"])
        return ok, f"ttm_after_11={before}, ttm_after_12={after}"
    if typ == "duplicate_month":
        try:
            normalize_monthly(pd.DataFrame({"month": data["months"], "revenue": data["revenue"]}))
        except ValueError as exc:
            return expected["raises"] in str(exc), str(exc)
        return False, "No validation error was raised"
    if typ == "missing_revenue":
        try:
            normalize_monthly(pd.DataFrame(data))
        except ValueError as exc:
            return expected["raises"] in str(exc), str(exc)
        return False, "No validation error was raised"
    if typ == "expense_category":
        df = pd.DataFrame({"month": data["months"], "expense_category": [data["category"]] * 2, "expense_amount": data["amounts"]})
        out = category_summary(df)
        last = out.iloc[-1]
        ok = approx(last["expense_mom_change"], expected["absolute_change"]) and approx(last["expense_mom_pct"], expected["percentage_change"])
        return ok, f"change={last['expense_mom_change']}, pct={last['expense_mom_pct']}"
    if typ == "short_history_commentary":
        months = pd.date_range("2025-01-01", periods=data["months"], freq="MS")
        out = normalize_monthly(pd.DataFrame({"month": months, "revenue": [data["revenue_each_month"]] * data["months"]}))
        text = " ".join(make_commentary(out))
        return expected["commentary_contains"].lower() in text.lower(), text
    return False, f"Unknown case type: {typ}"


def main():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    passed = 0
    print(f"Running {len(cases)} golden cases")
    for case in cases:
        try:
            ok, detail = run_case(case)
        except Exception as exc:  # Report the failure as an eval result, not a hidden crash.
            ok, detail = False, f"Unexpected {type(exc).__name__}: {exc}"
        print(f"{'PASS' if ok else 'FAIL'} {case['id']} — {case['name']}: {detail}")
        passed += int(ok)
    print(f"\nScore: {passed}/{len(cases)} ({passed / len(cases):.0%})")
    return 0 if passed == len(cases) else 1

if __name__ == "__main__":
    raise SystemExit(main())
