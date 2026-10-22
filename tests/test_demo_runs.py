"""scripts/new_run.py: numbered demo run folders. Uses a temp --root, never demo_runs/ and never outputs/."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import new_run  # noqa: E402

RUN_FIELDS = ["run_number", "run_id", "client", "month", "started", "finished", "git_branch", "git_head",
              "workbook_sha256_16", "stages", "grade_attempts", "retry_used", "reviewer_first_verdict",
              "reviewer_final_verdict", "final_grade", "pack_path", "open_question_count"]


def snapshot(folder):
    return {p.relative_to(folder).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns) for p in folder.rglob("*") if p.is_file()}


def cli(*args):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "new_run.py"), *args], capture_output=True, text=True,
                          encoding="utf-8", cwd=ROOT)


@unittest.skipUnless((ROOT / "clients" / "abc" / "config.yaml").is_file(), "client abc not present")
class NumberedRuns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "demo_runs"
        cls.before = snapshot(ROOT / "outputs")
        cls.r1, cls.r2 = (cli("abc", "2026-06", "--root", str(cls.root)) for _ in range(2))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_two_runs_make_output_001_and_002(self):
        self.assertEqual(self.r1.returncode, 0, self.r1.stdout + self.r1.stderr)
        self.assertEqual(self.r2.returncode, 0, self.r2.stdout + self.r2.stderr)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["output_001", "output_002"])
        self.assertTrue(self.r1.stdout.strip().endswith("output_001"))
        self.assertTrue(self.r2.stdout.strip().endswith("output_002"))
        for n in ("output_001", "output_002"):
            self.assertTrue((self.root / n / "abc" / "review_packet_2026-06.json").is_file())
        a, b = (self.root / n / "abc" / "review_packet_2026-06.json" for n in ("output_001", "output_002"))
        self.assertNotEqual(a, b)
        self.assertEqual(json.loads(a.read_text(encoding="utf-8")), json.loads(b.read_text(encoding="utf-8")))  # same inputs, separate files

    def test_nothing_written_to_outputs(self):
        self.assertEqual(snapshot(ROOT / "outputs"), self.before)

    def test_run_json_has_every_field(self):
        run = json.loads((self.root / "output_001" / "run.json").read_text(encoding="utf-8"))
        self.assertEqual([k for k in RUN_FIELDS if k not in run], [])
        self.assertEqual((run["run_number"], run["client"], run["month"]), (1, "abc", "2026-06"))
        for t in ("started", "finished"):
            self.assertEqual(sorted(run[t]), ["ist", "utc"])
        self.assertTrue(run["started"]["ist"].endswith("+05:30"))
        self.assertEqual(len(run["workbook_sha256_16"]), 16)
        self.assertEqual(run["stages"]["Intake"], "done")
        self.assertEqual(run["stages"]["Calculate"], "done")

    def test_finish_records_the_later_stages(self):
        folder = self.root / "output_002"
        out = folder / "abc"
        (out / "commentary_2026-06.md").write_text("## Headline\n1. x\n", encoding="utf-8")
        (out / "commentary_grade_2026-06.json").write_text(json.dumps({
            "retry_used": True, "attempts": [{"passed": False, "numbers": "1/2", "mismatches": ["m"]},
                                             {"passed": True, "numbers": "2/2", "mismatches": []}]}), encoding="utf-8")
        (out / "review_2026-06_first.json").write_text(json.dumps({"verdict": "changes"}), encoding="utf-8")
        (out / "review_2026-06.json").write_text(json.dumps({"verdict": "approve", "open_questions": [{}, {}]}), encoding="utf-8")
        (out / "commentary_final_grade_2026-06.json").write_text(json.dumps({"passed": True, "numbers": "2/2", "mismatches": []}), encoding="utf-8")
        (out / "monthly_review_2026-06.xlsx").write_bytes(b"x")
        (out / "owner_memo_2026-06.md").write_text("m", encoding="utf-8")
        run = new_run.finish(folder)
        self.assertEqual([a["passed"] for a in run["grade_attempts"]], [False, True])
        self.assertEqual((run["reviewer_first_verdict"], run["reviewer_final_verdict"]), ("changes", "approve"))
        self.assertTrue(run["final_grade"]["passed"])
        self.assertEqual((run["retry_used"], run["open_question_count"]), (True, 2))
        self.assertEqual(run["pack_path"], "abc/monthly_review_2026-06.xlsx")
        self.assertEqual(run["stages"]["Package"], "done")


class Refusals(unittest.TestCase):
    def test_invalid_client_is_refused_before_any_folder_exists(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "demo_runs"
            for client, month in (("../x", "2026-06"), ("ABC", "2026-06"), ("nosuchclient", "2026-06"), ("abc", "June")):
                r = cli(client, month, "--root", str(root))
                self.assertEqual(r.returncode, 2, (client, r.stdout))
                self.assertIn("ERROR", r.stdout)
            self.assertFalse(root.exists())

    def test_numbering_never_reuses_a_folder(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "output_005").mkdir()
            self.assertEqual(new_run.next_folder(root)[1].name, "output_006")
            self.assertEqual(new_run.next_folder(root)[1].name, "output_007")


if __name__ == "__main__":
    unittest.main()
