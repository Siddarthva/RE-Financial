"""Generate the synthetic XYZ Labs dataset (14 months, Apr 2025 - May 2026). Fictional data.

Deliberately differs from ABC: sheet name, label column, account names, month label format,
oldest-first column order, April fiscal year, a finance-cost line below operating profit, and
no Sales & Marketing accounts at all (a declared category with no source data).

    python clients/xyz/generate_dataset.py
"""
import random
from pathlib import Path
import pandas as pd
from openpyxl import Workbook

OUT = Path(__file__).resolve().parent / "xyz_financials.xlsx"
MONTHS = pd.date_range("2025-04-01", periods=14, freq="MS")


def series(rng, start, growth, noise):
    return [round(start * (1 + growth) ** i * (1 + rng.uniform(-noise, noise)), 2) for i in range(len(MONTHS))]


def main():
    rng = random.Random(20251012)
    revenue = {
        "Subscription Revenue": series(rng, 820000, 0.025, 0.03),
        # Implementation fees are lumpy: only in some months.
        "Implementation Fees": [round(v, 2) if i % 3 == 0 else 0.0 for i, v in enumerate(series(rng, 150000, 0.0, 0.2))],
    }
    cost_of_sales = {
        "Cloud Infrastructure": series(rng, 160000, 0.02, 0.05),
        "Support Staff Salaries": series(rng, 120000, 0.01, 0.01),
    }
    expenses = {
        "Salaries & Wages": series(rng, 410000, 0.01, 0.01),
        "Employer PF & ESI": series(rng, 49000, 0.01, 0.01),
        "Office Lease": [95000.0] * 12 + [104500.0] * 2,   # 10% escalation from Apr 2026
        "Utilities": series(rng, 18000, 0.0, 0.15),
        "SaaS Subscriptions": series(rng, 62000, 0.015, 0.04),
        "Audit Fees": [0.0] * 5 + [240000.0] + [0.0] * 8,   # one-off: statutory audit, Sep 2025
        "Legal Counsel": series(rng, 25000, 0.0, 0.3),
        "Depreciation & Amortisation": [31000.0] * 14,
    }
    finance_costs = series(rng, 14000, -0.01, 0.0)

    def total(block):
        return [round(sum(v[i] for v in block.values()), 2) for i in range(len(MONTHS))]

    rev_t, cos_t, exp_t = total(revenue), total(cost_of_sales), total(expenses)
    gross = [round(r - c, 2) for r, c in zip(rev_t, cos_t)]
    op = [round(g - e, 2) for g, e in zip(gross, exp_t)]
    net = [round(o - f, 2) for o, f in zip(op, finance_costs)]

    wb = Workbook()
    ws = wb.active
    ws.title = "P&L"
    ws.append(["XYZ Labs Pvt Ltd — synthetic test client (fictional)"])
    ws.append(["Monthly Profit & Loss, INR"])
    ws.append([])
    ws.append(["Line Item", *[m.strftime("%b-%y") for m in MONTHS]])
    rows = [("Revenue", None), *revenue.items(), ("Total Revenue", rev_t),
            ("Cost of Sales", None), *cost_of_sales.items(), ("Total Cost of Sales", cos_t),
            ("Gross Margin", gross),
            ("Expenses", None), *expenses.items(), ("Total Expenses", exp_t),
            ("Operating Profit", op), ("Finance Costs", finance_costs), ("Net Profit", net)]
    for label, values in rows:
        ws.append([label, *(values or [])])
    wb.save(OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
