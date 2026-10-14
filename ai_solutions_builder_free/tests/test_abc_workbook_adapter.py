import sys
import tempfile
import unittest
from pathlib import Path
import pandas as pd
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import abc_workbook_adapter as adapter
from abc_workbook_adapter import (
    parse_wide_income_statement, build_monthly_summary, build_expense_category_trends, generate_commentary,
)

SOURCE = ROOT / "ABC Inc - Financial Statements.xlsx"


def write_income_statement(path, months, rows):
    """Write a sheet in the ABC layout: section headers/totals in column A, accounts in column B.

    rows: list of (col_a, col_b, values) where values is None or a list aligned with months.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Income Statement"
    ws.append(["Income Statement (Profit and Loss)"])
    ws.append(["Test Co"])
    ws.append([])
    ws.append([])
    ws.append([None, "Account", *months])  # newest first, as in the source
    ws.append([])
    for col_a, col_b, values in rows:
        ws.append([col_a, col_b, *(values or [])])
    wb.save(path)


def simple_rows(n, extra_after_opex=()):
    return [
        ("Income", None, None),
        (None, "Sales", [100.0] * n),
        ("Total Income", None, [100.0] * n),
        ("Cost of Goods Sold", None, None),
        (None, "Hosting", [20.0] * n),
        ("Total Cost of Goods Sold", None, [20.0] * n),
        (None, "Gross Profit", [80.0] * n),
        ("Operating Expenses", None, None),
        (None, "Rent", [30.0] * n),
        (None, "Travel", [10.0] * n),
        ("Total Operating Expenses", None, [40.0] * n),
        *extra_after_opex,
        (None, "Operating Income", [40.0] * n),
        (None, "Net Income", [40.0] * n),
    ]


class AdapterBugRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "wb.xlsx"
        adapter.__dict__.pop("INPUT_PATH", None)

    def tearDown(self):
        self.tmp.cleanup()

    def test_bug1_mom_pct_sign_uses_absolute_prior_for_negative_base(self):
        # Net loss shrinking from -339,099.60 to -330,756.08 is an improvement: the % must be positive.
        monthly = pd.DataFrame({
            "month": pd.to_datetime(["2026-05-01", "2026-06-01"]),
            "net_income": [-339099.60, -330756.08],
        })
        line = [n for n in generate_commentary(monthly) if n.startswith("Net income")][0]
        self.assertIn("+8,343.52", line)
        self.assertIn("(+2.5%)", line)

    def test_bug2_expense_trends_do_not_depend_on_module_global(self):
        months = ["Feb 2025", "Jan 2025"]
        write_income_statement(self.path, months, simple_rows(2))
        am = parse_wide_income_statement(self.path)
        out = build_expense_category_trends(am)  # previously NameError: INPUT_PATH
        self.assertEqual(sorted(out["expense_category"].unique()), ["Rent", "Travel"])

    def test_bug3_rows_after_total_operating_expenses_are_not_opex(self):
        months = ["Feb 2025", "Jan 2025"]
        extra = [(None, "Other Income", [5.0, 5.0])]
        write_income_statement(self.path, months, simple_rows(2, extra))
        am = parse_wide_income_statement(self.path)
        cats = build_expense_category_trends(am)
        self.assertNotIn("Other Income", set(cats["expense_category"]))
        jan = cats[cats["month"] == pd.Timestamp("2025-01-01")]
        self.assertEqual(jan["amount"].sum(), 40.0)

    def test_bug4_summary_ttm_requires_consecutive_calendar_months(self):
        # 12 columns but July 2025 is missing, so no valid TTM window exists.
        dates = pd.to_datetime([
            "2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01", "2025-05-01", "2025-06-01",
            "2025-08-01", "2025-09-01", "2025-10-01", "2025-11-01", "2025-12-01", "2026-01-01",
        ])
        months = [d.strftime("%b %Y") for d in sorted(dates, reverse=True)]
        write_income_statement(self.path, months, simple_rows(12))
        summary = build_monthly_summary(parse_wide_income_statement(self.path))
        self.assertTrue(summary["revenue_ttm"].isna().all())

    def test_bug5_category_mom_pct_sign_uses_absolute_prior(self):
        # Source: Income Tax Benefit I101 = -1,244,429.84 (Dec 2025) -> H101 = 0 (Jan 2026).
        months = ["Feb 2025", "Jan 2025"]
        rows = simple_rows(2)
        rows.insert(9, (None, "Income Tax Benefit", [0.0, -1000.0]))
        write_income_statement(self.path, months, rows)
        cats = build_expense_category_trends(parse_wide_income_statement(self.path))
        feb = cats[(cats["expense_category"] == "Income Tax Benefit") & (cats["month"] == pd.Timestamp("2025-02-01"))].iloc[0]
        self.assertEqual(feb["mom_change"], 1000.0)
        self.assertEqual(feb["mom_pct"], 1.0)

    def test_ttm_available_for_twelve_consecutive_months(self):
        months = [d.strftime("%b %Y") for d in pd.date_range("2025-01-01", periods=12, freq="MS")[::-1]]
        write_income_statement(self.path, months, simple_rows(12))
        summary = build_monthly_summary(parse_wide_income_statement(self.path))
        self.assertEqual(summary["revenue_ttm"].iloc[-1], 1200.0)
        self.assertTrue(summary["revenue_ttm"].iloc[:-1].isna().all())


@unittest.skipUnless(SOURCE.exists(), "source workbook not present")
class SourceWorkbookReconciliationTests(unittest.TestCase):
    """Read-only regression checks against the supplied workbook's own totals."""

    @classmethod
    def setUpClass(cls):
        cls.am = parse_wide_income_statement(SOURCE)
        cls.summary = build_monthly_summary(cls.am).set_index("month")
        cls.cats = build_expense_category_trends(cls.am)

    def test_months_parsed_ascending_without_gaps(self):
        months = list(self.am.columns)
        self.assertEqual(months, list(pd.date_range("2025-01-01", "2026-06-01", freq="MS")))

    def test_opex_categories_sum_to_total_operating_expenses_every_month(self):
        sums = self.cats.groupby("month")["amount"].sum()
        for month, total in self.summary["operating_expenses"].items():
            self.assertAlmostEqual(sums[month], total, places=2, msg=str(month))

    def test_subtotal_rows_excluded_from_categories(self):
        names = set(self.cats["expense_category"])
        for subtotal in ["Total S & M Payroll", "Total Marketing", "S & M Payroll", "Marketing",
                         "Total Operating Expenses", "Operating Income", "Net Income"]:
            self.assertNotIn(subtotal, names)

    def test_spot_cells(self):
        # Values read from the source cells: T = Jan 2025, O = Jun 2025, C = Jun 2026.
        jun26 = pd.Timestamp("2026-06-01")
        self.assertAlmostEqual(self.summary.at[jun26, "revenue"], 195898.16, places=2)        # C14
        self.assertAlmostEqual(self.summary.at[jun26, "net_income"], -330756.08, places=2)    # C107
        self.assertAlmostEqual(self.am.at["Bad Debts", jun26], -1806.24, places=2)            # C31

    def test_balance_sheet_cash_and_runway(self):
        import abc_workbook_adapter as abc
        bs = parse_wide_income_statement(SOURCE, abc.ABC_BS_LAYOUT)
        pos = abc.cash_position(bs)
        self.assertEqual(pos["month"], pd.Timestamp("2026-06-01"))                         # BS col D = 30 Jun 2026
        self.assertAlmostEqual(pos["cash"], 713481.26, places=2)                           # BS D15
        self.assertAlmostEqual(pos["burn"][3], 209656.62, places=2)                        # (G15 - D15) / 3
        self.assertAlmostEqual(pos["runway_months"][3], 3.403094, places=6)

    def test_current_year_earnings_ties_to_ytd_net_income(self):
        import abc_workbook_adapter as abc
        bs = parse_wide_income_statement(SOURCE, abc.ABC_BS_LAYOUT)
        ytd = self.summary.loc["2026-01-01":"2026-06-01", "net_income"].sum()
        self.assertAlmostEqual(bs.at["Current Year Earnings", pd.Timestamp("2026-06-01")], -1987916.44, places=2)  # BS D63
        self.assertAlmostEqual(ytd, -1987916.44, places=2)

    def test_cash_position_no_burn_gives_no_runway(self):
        import abc_workbook_adapter as abc
        months = pd.date_range("2026-01-01", periods=4, freq="MS")
        bs = pd.DataFrame([[100.0, 110.0, 120.0, 130.0]], index=[abc.ABC_CASH_ROW], columns=months)
        pos = abc.cash_position(bs, windows=(1, 3, 6))
        self.assertIsNone(pos["runway_months"][1])  # cash rose: no burn, so no runway
        self.assertIsNone(pos["runway_months"][6])  # history too short


if __name__ == "__main__":
    unittest.main()
