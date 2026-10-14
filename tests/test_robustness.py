"""Regression tests for the defects found by 03_evals/robustness/fault_injection.py (Phase 2, 2026-10-14).

Each test builds a perturbed values-only COPY of the ABC workbook in a temp folder; the source is only read.
The full fault suite (32 faults, both entry points) is `python 03_evals/robustness/fault_injection.py`.
"""
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import abc_workbook_adapter as engine  # noqa: E402
import close_artifacts as ca  # noqa: E402
import monthly_review as mr  # noqa: E402
import run_client  # noqa: E402

SOURCE = ROOT / "data" / "ABC Inc - Financial Statements.xlsx"
IS = "Income Statement"


def copy_with(tmp: Path, edit=None, name="book.xlsx") -> Path:
    wb = load_workbook(io.BytesIO(SOURCE.read_bytes()), data_only=True)
    if edit:
        edit(wb)
    path = tmp / name
    wb.save(path)
    return path


def set_cell(ref, value):
    return lambda wb: wb[IS].__setitem__(ref, value) or None


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = run_client.load_config("abc")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def gate(self, path, month="2026-06"):
        """The intake gate's message for a workbook, or None if it is accepted."""
        cfg = {**self.cfg, "workbook_path": path}
        try:
            report, _, _ = ca.intake_gate(cfg, month, engine)
        except ValueError as exc:
            return str(exc)
        return ca.refusal(report, month)


class NumberParsing(unittest.TestCase):
    def test_money_text_and_bad_values(self):
        cases = {"$1,234.50": 1234.5, "(1,234)": -1234.0, "-$1,234": -1234.0, "($5.25)": -5.25, " 7 ": 7.0, 12.5: 12.5}
        for raw, want in cases.items():
            self.assertEqual(engine.to_number(raw), (want, None), raw)
        for raw in ("n/a", "NaN", "inf", "#DIV/0!", float("inf")):
            value, why = engine.to_number(raw)
            self.assertIsNone(value, raw)
            self.assertNotEqual(why, "blank", raw)


class ParserFaults(Base):
    def test_na_text_is_a_bad_cell_not_a_silent_blank(self):  # F12: pandas' default NA list hid it
        am = engine.parse_wide_income_statement(copy_with(self.tmp, set_cell("C11", "n/a")))
        self.assertEqual([b[0] for b in am.attrs["bad_cells"]], ["Income Statement!C11"])
        self.assertEqual(am.attrs["blank_cells"], [])

    def test_currency_text_is_read_as_the_same_number(self):  # F14/F15
        am0 = engine.parse_wide_income_statement(SOURCE)
        v = am0.at["Usage Fees", pd.Timestamp("2026-06-01")]
        am = engine.parse_wide_income_statement(copy_with(self.tmp, set_cell("C11", f"${v:,.2f}")))
        self.assertEqual(am.at["Usage Fees", pd.Timestamp("2026-06-01")], v)

    def test_duplicate_month_raises_naming_both_cells(self):  # F03
        def dup(wb):
            wb[IS]["D5"] = "Jun 2026"
        with self.assertRaisesRegex(ValueError, "Jun 2026 appears twice, in cells C5 and D5"):
            engine.parse_wide_income_statement(copy_with(self.tmp, dup))


class IntakeGate(Base):
    def test_clean_copy_passes(self):
        self.assertIsNone(self.gate(copy_with(self.tmp)))

    def test_excel_error_value_stops(self):  # F19: pandas reads error cells as blanks
        msg = self.gate(copy_with(self.tmp, set_cell("C33", "#DIV/0!")))
        self.assertIn("Excel error value (C33 #DIV/0!)", msg)

    def test_line_that_does_not_foot_stops(self):  # F26
        def bump(wb):
            wb[IS]["F11"] = wb[IS]["F11"].value + 1000
        self.assertIn("Total Income foots to its lines (every month) at Income Statement!F14", self.gate(copy_with(self.tmp, bump)))

    def test_missing_prior_month_stops(self):  # F01
        self.assertIn("no column for 2026-05", self.gate(copy_with(self.tmp, set_cell("D5", None))))

    def test_corrupt_and_locked_files_stop_with_a_cause(self):  # F29, F31
        bad = self.tmp / "bad.xlsx"
        bad.write_bytes(b"not a workbook")
        self.assertIn("Not a valid .xlsx workbook", self.gate(bad))
        if sys.platform == "win32":
            import msvcrt
            path = copy_with(self.tmp)
            with open(path, "r+b") as f:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, path.stat().st_size)
                try:
                    self.assertIn("open or locked", self.gate(path))
                finally:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, path.stat().st_size)


class SkillPathUsesTheGate(Base):
    def test_prepare_refuses_a_non_footing_workbook_and_writes_nothing(self):
        """The /monthly-analysis path (monthly_review.prepare) used to skip intake and succeed with wrong numbers."""
        clients, outputs = self.tmp / "clients", self.tmp / "outputs"
        (clients / "abc").mkdir(parents=True)
        text = (ROOT / "clients" / "abc" / "config.yaml").read_text(encoding="utf-8").splitlines()
        (clients / "abc" / "config.yaml").write_text("\n".join("workbook: book.xlsx" if l.startswith("workbook:") else l for l in text),
                                                      encoding="utf-8")
        def bump(wb):
            wb[IS]["F11"] = wb[IS]["F11"].value + 1000
        shutil.move(copy_with(self.tmp, bump), clients / "abc" / "book.xlsx")
        with self.assertRaisesRegex(ValueError, "Total Income foots"):
            mr.prepare("abc", "2026-06", clients, outputs)
        self.assertEqual([p.name for p in (outputs / "abc").glob("*") if p.is_file()], [])


class GapsAndWarnings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.am = engine.parse_wide_income_statement(SOURCE)

    def gapped(self, drop):
        am = self.am.drop(columns=[pd.Timestamp(m) for m in drop])
        am.attrs = dict(self.am.attrs)
        return am, engine.build_monthly_summary(am)

    def test_no_mom_across_a_gap_and_prior_month_required(self):
        am, monthly = self.gapped(["2026-02-01"])
        packet = mr.build_computed(am, monthly.set_index("month"), pd.Timestamp("2026-06-01"))
        self.assertNotIn("mom_change", packet["months"]["2026-03"]["revenue"])
        self.assertIn("mom_change", packet["months"]["2026-04"]["revenue"])
        am, monthly = self.gapped(["2026-05-01"])
        with self.assertRaisesRegex(ValueError, "needs its prior month 2026-05"):
            mr.build_computed(am, monthly.set_index("month"), pd.Timestamp("2026-06-01"))

    def test_margin_flags_skip_a_gap(self):
        _, monthly = self.gapped(["2026-04-01"])  # without the gap rule, May 2026 vs Mar 2026 shows as a >5 pp "drop"
        flagged = [f["month"] for f in engine.margin_drop_flags(monthly, 5)]
        self.assertEqual(flagged, ["2025-03", "2025-08"])

    def test_gap_warning_names_the_month(self):  # F02: the warning itself used to crash on Period formatting
        cfg = run_client.load_config("abc")
        am, monthly = self.gapped(["2025-09-01"])
        trends = engine.build_expense_category_trends(am, cfg["subtotal_rows"])
        rollup = engine.build_category_rollup(trends, cfg["account_to_category"])
        warnings = run_client.data_quality(cfg, am, monthly, trends, rollup)
        self.assertTrue(any("Months missing from the source: Sep 2025" in w for w in warnings), warnings)

    def test_outlier_and_lookalike_warnings_and_none_on_clean_data(self):
        self.assertEqual(run_client.cell_warnings(self.am), [])
        am = self.am.rename(index={"Bonus": "Bοnus"})
        am.attrs = dict(self.am.attrs)
        am.loc["Usage Fees", pd.Timestamp("2026-06-01")] *= 1000
        text = " ".join(run_client.cell_warnings(am))
        self.assertIn("Possible outlier: Usage Fees in Jun 2026", text)
        self.assertIn("non-ASCII", text)


if __name__ == "__main__":
    unittest.main()
