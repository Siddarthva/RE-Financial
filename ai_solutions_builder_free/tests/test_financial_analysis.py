import sys
import unittest
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from financial_analysis import normalize_monthly, category_summary, make_commentary

class FinancialAnalysisTests(unittest.TestCase):
    def sample(self, n=13):
        months = pd.date_range("2025-01-01", periods=n, freq="MS")
        return pd.DataFrame({
            "month": months,
            "revenue": [1000 + 100*i for i in range(n)],
            "gross_profit": [400 + 40*i for i in range(n)],
            "operating_expenses": [250 + 10*i for i in range(n)],
            "net_income": [100 + 20*i for i in range(n)],
        })

    def test_mom_revenue_change(self):
        out = normalize_monthly(self.sample(2))
        self.assertEqual(out.loc[1, "revenue_mom_change"], 100)
        self.assertAlmostEqual(out.loc[1, "revenue_mom_pct"], 100/1000)

    def test_ttm_only_after_12_months(self):
        out = normalize_monthly(self.sample(13))
        self.assertTrue(pd.isna(out.loc[10, "revenue_ttm"]))
        self.assertEqual(out.loc[11, "revenue_ttm"], sum([1000 + 100*i for i in range(12)]))
        self.assertEqual(out.loc[12, "revenue_ttm"], sum([1000 + 100*i for i in range(1, 13)]))

    def test_ttm_rejects_month_gap(self):
        months = [pd.Timestamp(x) for x in [
            "2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01",
            "2025-05-01", "2025-06-01", "2025-08-01", "2025-09-01",
            "2025-10-01", "2025-11-01", "2025-12-01", "2026-01-01"
        ]]  # July is missing; there are still 12 rows.
        df = pd.DataFrame({"month": months, "revenue": [100] * 12})
        out = normalize_monthly(df)
        self.assertTrue(pd.isna(out.iloc[-1]["revenue_ttm"]))

    def test_margin_calculation(self):
        out = normalize_monthly(self.sample(1))
        self.assertAlmostEqual(out.loc[0, "gross_margin_pct"], 0.4)
        self.assertAlmostEqual(out.loc[0, "net_margin_pct"], 0.1)

    def test_duplicate_months_rejected(self):
        df = self.sample(2)
        df.loc[1, "month"] = df.loc[0, "month"]
        with self.assertRaisesRegex(ValueError, "one row per month"):
            normalize_monthly(df)

    def test_missing_required_column_rejected(self):
        with self.assertRaisesRegex(ValueError, "Missing required columns"):
            normalize_monthly(pd.DataFrame({"month": ["2025-01-01"]}))

    def test_category_mom(self):
        df = pd.DataFrame({
            "month": ["2025-01-01", "2025-02-01", "2025-01-01", "2025-02-01"],
            "expense_category": ["Rent", "Rent", "Payroll", "Payroll"],
            "expense_amount": [100, 110, 200, 180],
        })
        out = category_summary(df)
        rent_feb = out[(out["expense_category"] == "Rent") & (out["month"] == pd.Timestamp("2025-02-01"))].iloc[0]
        self.assertEqual(rent_feb["expense_mom_change"], 10)
        self.assertAlmostEqual(rent_feb["expense_mom_pct"], 0.1)

if __name__ == "__main__":
    unittest.main()
