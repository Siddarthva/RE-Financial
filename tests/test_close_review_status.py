"""close_review_status stops at the first failed gate and never reports approval it has not seen."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import close_review_status as crs  # noqa: E402

SRC = ROOT / "outputs" / "abc"
M = "2026-06"
FILES = [f"intake_{M}.json", f"review_packet_{M}.json", f"flux_{M}.json", f"commentary_{M}.md", f"review_{M}.json",
         f"flux_explanations_{M}.md", f"client_questions_{M}.md", f"monthly_review_{M}.xlsx"]


class Status(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        for f in FILES:
            shutil.copy(SRC / f, self.d / f)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def states(self):
        return [r[1] for r in crs.evaluate(self.d, M)]

    def test_all_pass_then_waits_for_human(self):
        self.assertEqual(self.states(), ["PASS"] * 5 + ["WAITING"])

    def test_approved_record_passes_stage_6(self):
        (self.d / f"approval_{M}.json").write_text(json.dumps({"status": "approved", "reviewer": "T"}))
        self.assertEqual(self.states(), ["PASS"] * 6)

    def test_missing_intake_stops_everything(self):
        (self.d / f"intake_{M}.json").unlink()
        self.assertEqual(self.states(), ["NOT RUN"] * 6)

    def test_failed_intake_check_stops_at_stage_1(self):
        p = self.d / f"intake_{M}.json"
        j = json.loads(p.read_text())
        j["checks"][0]["passed"] = False
        p.write_text(json.dumps(j))
        self.assertEqual(self.states(), ["FAIL"] + ["NOT RUN"] * 5)

    def test_reviewer_changes_verdict_stops_at_stage_4(self):
        p = self.d / f"review_{M}.json"
        j = json.loads(p.read_text())
        j["verdict"] = "changes"
        p.write_text(json.dumps(j))
        self.assertEqual(self.states(), ["PASS"] * 3 + ["FAIL", "NOT RUN", "NOT RUN"])

    def test_bad_client_question_fails_package(self):
        p = self.d / f"client_questions_{M}.md"
        p.write_text(p.read_text().replace("13,126.41", "13,162.41"))
        self.assertEqual(self.states(), ["PASS"] * 4 + ["FAIL", "NOT RUN"])


if __name__ == "__main__":
    unittest.main()
