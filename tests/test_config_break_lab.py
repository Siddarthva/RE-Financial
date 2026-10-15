"""Config mistakes must stop at intake with a message, never run quietly on wrong data (02_skill/config_break_lab.py)."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("config_break_lab", ROOT / "02_skill" / "config_break_lab.py")
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)
CASES = {c[0]: c for c in lab.CASES}


class ConfigBreakTests(unittest.TestCase):
    def test_baseline_runs(self):
        self.assertEqual(lab.run_case(CASES["baseline"])["exit"], 0)

    def test_wrong_section_header_is_refused_at_intake(self):
        r = lab.run_case(CASES["section_header_wrong"])
        self.assertEqual((r["exit"], r["stopped_at"]), (1, "Intake"))
        self.assertIn("Section header matched", r["message"] + str(r))

    def test_text_threshold_is_refused_with_a_clear_message(self):
        r = lab.run_case(CASES["margin_drop_text"])
        self.assertEqual((r["exit"], r["stopped_at"]), (1, "Intake"))
        self.assertIn("gross_margin_drop_pp must be", r["message"])

    def test_unmapped_account_runs_with_a_warning(self):
        r = lab.run_case(CASES["account_unmapped"])
        self.assertEqual(r["exit"], 0)
        self.assertGreater(r["warnings"], lab.run_case(CASES["baseline"])["warnings"])


if __name__ == "__main__":
    unittest.main()
