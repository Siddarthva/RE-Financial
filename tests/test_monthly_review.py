"""Packet, sign-off pack and verdict logic of src/monthly_review.py (runs in a temporary outputs folder)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import monthly_review as mr  # noqa: E402

GOOD = """# ABC Inc - Jun 2026
1. Revenue was $195,898.16, down $12,452.80 (-6.0%) from May 2026.
2. Gross margin was 70.2%.
3. Events & Conferences (+$17,970.67), Bad Debts (-$14,741.53) and Usage Fees (-$11,142.74) moved most.
4. Cash is $713,481.26; runway is about 3.4 months at the 3-month average burn.
"""
APPROVE = {"verdict": "approve", "changes": [], "statement_notes": [{"statement": i, "status": "ok", "note": ""} for i in range(1, 5)],
           "open_questions": [{"question": "Why did Usage Fees fall?", "why": "Largest revenue movement."}]}


class MonthlyReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        cls.packet_path = mr.prepare("abc", "2026-06", outputs_root=cls.out)
        cls.packet = json.loads(cls.packet_path.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def build(self, commentary, review, month="2026-06"):
        d = self.out / "abc"
        (d / "c.md").write_text(commentary, encoding="utf-8")
        (d / "r.json").write_text(json.dumps(review), encoding="utf-8")
        return mr.build("abc", month, d / "c.md", d / "r.json", outputs_root=self.out)

    def test_gross_margin_drop_flags(self):
        self.assertEqual(self.packet["gross_margin_drop_threshold_pp"], 5)
        self.assertEqual([f["month"] for f in self.packet["gross_margin_flags"]], ["2025-03", "2025-08", "2026-04"])
        self.assertTrue(all(f["change_pp"] < -5 for f in self.packet["gross_margin_flags"]))

    def test_packet_has_source_cell_values(self):
        jun = self.packet["months"]["2026-06"]
        self.assertAlmostEqual(jun["revenue"]["value"], 195898.16, places=2)       # C14
        self.assertAlmostEqual(jun["net_income"]["value"], -330756.08, places=2)   # C107
        self.assertEqual([m["account"] for m in self.packet["top_movements"]], ["Events & Conferences", "Bad Debts", "Usage Fees"])
        self.assertAlmostEqual(self.packet["cash"]["value"], 713481.26, places=2)  # Balance Sheet D15

    def test_month_without_prior_is_rejected(self):
        with self.assertRaises(ValueError):
            mr.prepare("abc", "2025-01", outputs_root=self.out)

    def test_approved_pack_has_blank_signoff_and_open_questions(self):
        path, approved = self.build(GOOD, APPROVE)
        self.assertTrue(approved)
        wb = openpyxl.load_workbook(path)
        self.assertEqual(wb.sheetnames, ["Summary", "Commentary Sign-off", "Numbers Check", "Top Movements", "Reviewer Changes", "Open Questions"])
        sheet = wb["Commentary Sign-off"]
        self.assertEqual(sheet["G1"].value, "Sign-off (name / date)")
        self.assertTrue(all(row[6].value is None for row in sheet.iter_rows(min_row=2)))
        questions = [r[2] for r in wb["Open Questions"].iter_rows(min_row=2, values_only=True)]
        self.assertIn("Why did Usage Fees fall?", questions)
        self.assertTrue(any("Runway" in q for q in questions))  # auto question: runway under 6 months

    def test_wrong_number_blocks_approval_even_if_reviewer_approves(self):
        path, approved = self.build(GOOD.replace("70.2%", "71.2%"), APPROVE)
        self.assertFalse(approved)
        row = [r for r in openpyxl.load_workbook(path)["Commentary Sign-off"].iter_rows(min_row=2, values_only=True) if r[0] == 2][0]
        self.assertIn("MISMATCH", row[2])
        self.assertEqual(row[5], "CHANGE")

    def test_reviewer_changes_block_approval(self):
        review = {**APPROVE, "verdict": "changes", "changes": [{"statement": 1, "type": "invented_cause", "issue": "x", "fix": "y"}]}
        self.assertFalse(self.build(GOOD, review)[1])

    def test_missing_cash_statement_blocks_approval(self):
        self.assertFalse(self.build("\n".join(GOOD.splitlines()[:-1]), APPROVE)[1])

    def test_commentary_numbering_is_enforced(self):
        with self.assertRaises(ValueError):
            mr.parse_statements("1. a\n3. b\n")

    def test_xyz_runs_without_cash_and_stays_in_its_folder(self):
        xyz = mr.prepare("xyz", "2026-03", outputs_root=self.out)
        self.assertEqual(xyz.parent.name, "xyz")
        self.assertNotIn("cash", json.loads(xyz.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
