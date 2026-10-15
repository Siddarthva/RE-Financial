"""Intake Balance Sheet checks: it balances every month, and Current Year Earnings = YTD net income.

Each failure case edits a values-only COPY of the ABC workbook in a temp folder; the source is only read.
"""
import sys
import unittest

import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_robustness import Base, copy_with, engine, ca  # noqa: E402

BS = "Balance Sheet"
BALANCES = "Balance Sheet balances (assets = liabilities + equity, every month)"
CYE = "Current Year Earnings = year-to-date net income (every month)"


def find_cell(wb, label, month_header):
    """Cell ref in the Balance Sheet for a row label and a month-end header like 2026-06."""
    ws = wb[BS]
    row = next(c.row for r in ws.iter_rows() for c in r if c.value == label)
    col = next(c.column_letter for r in ws.iter_rows(min_row=1, max_row=8) for c in r
               if c.value is not None and pd.to_datetime(str(c.value), format="%d %b %Y", errors="coerce") is not pd.NaT
               and f"{pd.to_datetime(str(c.value), format='%d %b %Y'):%Y-%m}" == month_header)
    return f"{col}{row}"


def bump(label, month, delta):
    def edit(wb):
        ref = find_cell(wb, label, month)
        wb[BS][ref] = wb[BS][ref].value + delta
    return edit


class BalanceSheetChecks(Base):
    def report(self, path, month="2026-06"):
        report, _, _ = ca.intake_gate({**self.cfg, "workbook_path": path}, month, engine)
        return {c["check"]: c for c in report["checks"]}, report

    def test_real_workbook_passes_both_checks(self):
        checks, report = self.report(copy_with(self.tmp))
        self.assertTrue(checks[BALANCES]["passed"])
        self.assertTrue(checks[CYE]["passed"])
        self.assertEqual(report["status"], "pass")

    def test_unbalanced_month_fails_with_cell_and_fix(self):
        checks, report = self.report(copy_with(self.tmp, bump("Total Assets", "2026-03", 250.0)))
        c = checks[BALANCES]
        self.assertFalse(c["passed"])
        self.assertRegex(c["cell_ref"], r"^Balance Sheet![A-Z]+\d+$")
        self.assertIn("2026-03", c["detail"])
        self.assertIn("Fix:", c["detail"])
        self.assertEqual(report["status"], "fail")
        self.assertIn("Balance Sheet balances", ca.refusal(report, "2026-06"))

    def test_current_year_earnings_mismatch_fails(self):
        checks, _ = self.report(copy_with(self.tmp, bump("Current Year Earnings", "2025-09", 1.0)))
        c = checks[CYE]
        self.assertFalse(c["passed"])
        self.assertIn("2025-09", c["detail"])
        self.assertTrue(checks[BALANCES]["passed"])

    def test_missing_row_stops_with_a_named_fix(self):
        def rename(wb):
            cell = next(c for r in wb[BS].iter_rows() for c in r if c.value == "Current Year Earnings")
            cell.value = "Earnings"
        checks, _ = self.report(copy_with(self.tmp, rename))
        c = checks["Balance Sheet rows present"]
        self.assertFalse(c["passed"])
        self.assertIn("Current Year Earnings", c["detail"])


if __name__ == "__main__":
    unittest.main()
