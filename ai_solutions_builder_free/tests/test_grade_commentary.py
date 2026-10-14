import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
from grade_commentary import extract_numbers, grade

COMPUTED = {
    "months": {"2026-06": {"revenue": {"value": 195898.16, "mom_change": -12452.80, "mom_pct": -0.059768},
                           "gross_profit": {"margin": 0.701516, "margin_change_pp": 0.66}}},
    "line_items": {"Usage Fees": {"value": 166781.50, "mom_change": -11142.74}},
    "top_movements": [{"account": "Events & Conferences", "mom_change": 17970.67},
                      {"account": "Bad Debts", "mom_change": -14741.53},
                      {"account": "Marketing/Advertising: Partner Marketing", "mom_change": -8394.63}],
    "cash": {"value": 713481.26, "prior_value": 929024.59, "mom_change": -215543.33,
             "burn": {"1m": 215543.33, "3m": 209656.62, "6m": 311972.673333},
             "runway_months": {"1m": 3.310152, "3m": 3.403094, "6m": 2.286999}},
}
NAMES = "Events & Conferences, Bad Debts and Partner Marketing moved most."
CASH = "Cash is $713,481 at month end; runway is about 3.4 months at the 3-month burn."


class GradeCommentaryTests(unittest.TestCase):
    def test_skips_years_counts_and_list_markers(self):
        tokens = [t for t, *_ in extract_numbers("1. In Jun 2026 (June 30), over 12 months, 3 questions remain.")]
        self.assertEqual(tokens, [])

    def test_accepts_values_within_display_rounding(self):
        text = f"Revenue was $195.9k, down $12,453 (6.0%); gross margin 70.2% (+0.7 pp). {NAMES} {CASH}"
        report = grade(text, COMPUTED)
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["numbers_checked"], 7)

    def test_wrong_number_fails(self):
        report = grade(f"Revenue was $196,898.16. {NAMES} {CASH}", COMPUTED)
        self.assertFalse(report["passed"])
        self.assertEqual(report["numbers_matched"], 2)  # only the cash and runway figures match

    def test_missing_top_movement_fails(self):
        report = grade(f"Revenue was $195,898.16; Events & Conferences and Bad Debts moved. {CASH}", COMPUTED)
        self.assertFalse(report["passed"])
        self.assertEqual([m["mentioned"] for m in report["top_movements"]], [True, True, False])

    def test_missing_cash_risk_fails(self):
        report = grade(f"Revenue was $195,898.16. {NAMES}", COMPUTED)
        self.assertFalse(report["passed"])
        self.assertFalse(report["cash_risk"]["covered"])

    def test_cash_without_runway_fails(self):
        report = grade(f"Revenue was $195,898.16. {NAMES} Cash ended at $713.5k.", COMPUTED)
        self.assertTrue(report["cash_risk"]["cash_stated"])
        self.assertFalse(report["cash_risk"]["runway_stated"])
        self.assertFalse(report["passed"])

    def test_wrong_runway_figure_fails(self):
        report = grade(f"Revenue was $195,898.16. {NAMES} Cash is $713,481; runway is 5 months.", COMPUTED)
        self.assertFalse(report["cash_risk"]["runway_stated"])
        self.assertFalse(report["passed"])

    def test_whole_number_runway_within_rounding_passes(self):
        report = grade(f"Revenue was $195,898.16. {NAMES} Cash is $713,481, a runway of about 3 months.", COMPUTED)
        self.assertTrue(report["cash_risk"]["covered"], report["cash_risk"])
        self.assertTrue(report["passed"])

    def test_engine_commentary_passes_grader_on_real_workbook(self):
        """Regression: engine text omitted top movements and cash/runway, and the skill said runway can't be computed."""
        import grade_commentary as gc
        am = gc.abc.parse_wide_income_statement(gc.WORKBOOK)
        cash = gc.abc.cash_position(gc.abc.parse_wide_income_statement(gc.WORKBOOK, gc.abc.ABC_BS_LAYOUT))
        text = "\n".join(gc.abc.generate_commentary(gc.abc.build_monthly_summary(am), am, cash))
        report = grade(text, gc.build_computed())
        self.assertTrue(all(m["mentioned"] for m in report["top_movements"]), report["top_movements"])
        self.assertTrue(report["cash_risk"]["covered"], report["cash_risk"])
        self.assertTrue(report["passed"])
        skill = (ROOT / ".claude" / "skills" / "monthly-financial-analysis" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("runway cannot be calculated", skill)


if __name__ == "__main__":
    unittest.main()
