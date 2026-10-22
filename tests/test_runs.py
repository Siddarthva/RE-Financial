"""scripts/new_run.py: permanent numbered run folders runs/runN/ with the full layout and per-run evals.

Every run here lives in a TEMP root. Nothing in this file creates, changes or deletes the real runs/ folder, and the
last test asserts that it is still there, unchanged.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import new_run  # noqa: E402

APP = ROOT / "05_review_workspace" / "app"
M = "2026-06"
REAL_RUNS = ROOT / "runs"
BEFORE_REAL = sorted(p.name for p in REAL_RUNS.iterdir()) if REAL_RUNS.is_dir() else None


def tree(root: Path) -> dict:
    """{relative path: sha256} of every file under root."""
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def cli(*args):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "new_run.py"), *map(str, args)], capture_output=True, text=True,
                          encoding="utf-8", cwd=ROOT)


PIPE_FILES = ["SUMMARY.md", "run.json", f"01_intake/intake_{M}.json", f"02_numbers/review_packet_{M}.json", f"02_numbers/flux_{M}.json",
              "02_numbers/analysis.xlsx", "03_commentary/NOT_RUN.md", "04_review/NOT_RUN.md", "05_evals/golden_results.txt",
              "05_evals/workbook_hash.txt", "05_evals/evals_summary.json", "06_pack/NOT_RUN.md", "logs/pipeline.log"]


class TwoPipelineRuns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "runs"
        cls.outputs_before = tree(ROOT / "outputs")
        cls.data_before = tree(ROOT / "data")
        cls.cli = cli("abc", M, "--root", cls.root)          # run1, through the command line
        n, cls.r2 = new_run.create("abc", M, cls.root)        # run2, through the function
        cls.r1 = cls.root / "run1"
        cls.outputs_after = tree(ROOT / "outputs")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_two_runs_create_run1_and_run2_with_the_full_layout(self):
        self.assertEqual(self.cli.returncode, 0, self.cli.stdout + self.cli.stderr)
        self.assertEqual(sorted(p.name for p in self.root.iterdir())[:2], ["run1", "run2"])  # a later test may add run3
        for d in (self.r1, self.r2):
            for rel in PIPE_FILES:
                self.assertTrue((d / rel).is_file(), f"{d.name}/{rel}")
            self.assertFalse((d / "_work").exists(), "the working folder is removed after the files are moved")
            self.assertEqual(sorted(p.name for p in d.iterdir() if p.is_dir()),
                             ["01_intake", "02_numbers", "03_commentary", "04_review", "05_evals", "06_pack", "logs"])

    def test_files_are_moved_not_copied(self):
        for d in (self.r1, self.r2):
            names = [p.name for p in d.rglob("*") if p.is_file() and p.name != "NOT_RUN.md"]
            self.assertEqual(len(names), len(set(names)), f"{d.name}: a file name appears twice")

    def test_cli_prints_the_folder_and_a_six_line_summary(self):
        lines = self.cli.stdout.strip().splitlines()
        self.assertTrue(lines[0].startswith("Run folder: ") and lines[0].endswith("run1"), lines[0])
        self.assertEqual(len(lines), 7)
        self.assertTrue(lines[1].startswith("1. run1"), lines[1])

    def test_nothing_is_written_to_outputs_and_data_is_unchanged(self):
        self.assertEqual(self.outputs_before, self.outputs_after)
        self.assertEqual(self.data_before, tree(ROOT / "data"))
        self.assertTrue(hashlib.sha256((ROOT / "data" / "ABC Inc - Financial Statements.xlsx").read_bytes()).hexdigest().startswith("75da8d679a89551f"))

    def test_pipeline_only_runs_say_claude_stages_were_not_run(self):
        for d in (self.r1, self.r2):
            for rel in ("03_commentary/NOT_RUN.md", "04_review/NOT_RUN.md", "06_pack/NOT_RUN.md"):
                self.assertIn("Claude stages were not run for this run", (d / rel).read_text(encoding="utf-8"))
            self.assertIn("Claude stages were not run for this run", (d / "SUMMARY.md").read_text(encoding="utf-8"))
            run = json.loads((d / "run.json").read_text(encoding="utf-8"))
            self.assertEqual((run["status"], run["kind"], run["mode"]), ("complete", "Pipeline only", "pipeline_only"))
            for stage in ("Intake", "Calculate", "Organize", "Evals"):
                self.assertTrue(run["timings"][stage]["started"] and run["timings"][stage]["ended"], stage)
                self.assertIn("duration_s", run["timings"][stage])

    def test_evals_summary_matches_the_eval_files(self):
        for d in (self.r1, self.r2):
            ev = d / "05_evals"
            summary = json.loads((ev / "evals_summary.json").read_text(encoding="utf-8"))
            golden = (ev / "golden_results.txt").read_text(encoding="utf-8")
            score = __import__("re").findall(r"Score:\s*(\d+)/(\d+)", golden)[-1]
            self.assertEqual(summary["golden"]["status"], "PASS" if score[0] == score[1] else "FAIL")
            self.assertIn(f"{score[0]}/{score[1]}", summary["golden"]["detail"])
            hashes = (ev / "workbook_hash.txt").read_text(encoding="utf-8")
            before, after = (ln.split(":", 1)[1].strip() for ln in hashes.splitlines()[:2])
            self.assertEqual(before == after and after.startswith("75da8d679a89551f"), summary["workbook_hash"]["status"] == "PASS")
            self.assertEqual(summary["commentary_grade"]["status"], "NOT_RUN")
            self.assertEqual(summary["flawed_control"]["status"], "NOT_RUN")
            self.assertEqual(json.loads((d / "run.json").read_text(encoding="utf-8"))["evals"], summary)

    def test_the_second_run_does_not_touch_the_first(self):
        again = tree(self.r1)
        new_run.create("abc", M, self.root)
        self.assertEqual({k: v for k, v in tree(self.r1).items() if not k.startswith("logs/")}, {k: v for k, v in again.items() if not k.startswith("logs/")})


class NumberingAndSorting(unittest.TestCase):
    def test_next_number_is_highest_plus_one_and_run10_sorts_after_run9(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "runs"
            for n in (2, 9):
                (root / f"run{n}").mkdir(parents=True)
            (root / "run7.bak").mkdir()          # not a run folder
            self.assertEqual(new_run.next_folder(root)[1].name, "run10")
            self.assertEqual(new_run.next_folder(root)[1].name, "run11")
            (root / "run11").rmdir()             # a freed number below the maximum is still not reused
            self.assertEqual(new_run.next_folder(root)[1].name, "run11")
            if APP.is_dir():
                sys.path.insert(0, str(APP))
                import data
                with mock.patch.object(data, "RUNS", root):
                    self.assertEqual([r.name for r in data.list_runs()], ["run11", "run10", "run9", "run2"])

    def test_invalid_input_makes_no_folder(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "runs"
            for client, month in (("nope", M), ("abc", "2026-13"), ("../x", M)):
                with self.assertRaises(ValueError):
                    new_run.create(client, month, root)
            self.assertFalse(root.exists())


class FailedRuns(unittest.TestCase):
    def test_a_failed_pipeline_keeps_the_folder_with_status_failed_error_and_log(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "runs"
            n, folder = new_run.create("abc", "2030-01", root)     # the workbook has no such month: intake refuses
            run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
            self.assertTrue(folder.is_dir())
            self.assertEqual(run["status"], "failed")
            self.assertTrue(run["errors"])
            self.assertTrue((folder / "logs" / "pipeline.log").read_text(encoding="utf-8").strip())
            self.assertIn("FAILED", (folder / "SUMMARY.md").read_text(encoding="utf-8").upper())
            self.assertFalse((folder / "_work").exists())
            self.assertEqual(cli("abc", "2030-01", "--root", root).returncode, 1)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["run1", "run2"])

    def test_an_exception_in_a_later_stage_is_recorded_and_the_folder_is_kept(self):
        with tempfile.TemporaryDirectory() as t:
            with mock.patch.object(new_run, "run_evals", side_effect=RuntimeError("boom")):
                n, folder = new_run.create("abc", M, Path(t) / "runs")
            run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(run["status"], "failed")
            self.assertTrue(any("boom" in e for e in run["errors"]))
            self.assertTrue((folder / "SUMMARY.md").is_file())

    def test_finish_with_failed_reason_keeps_an_unfinished_claude_run(self):
        with tempfile.TemporaryDirectory() as t:
            n, folder = new_run.create("abc", M, Path(t) / "runs", claude=True)
            self.assertEqual(json.loads((folder / "run.json").read_text(encoding="utf-8"))["status"], "running")
            self.assertTrue((folder / "_work" / "abc").is_dir())
            run = new_run.finalize(folder, failed="Claude session timeout")
            self.assertEqual(run["status"], "failed")
            self.assertIn("Claude session timeout", run["errors"])
            self.assertFalse((folder / "_work").exists())
            self.assertTrue((folder / f"02_numbers/review_packet_{M}.json").is_file())


class FullClaudeRun(unittest.TestCase):
    """The Claude stages are simulated by dropping the files /demo-run writes into _work, then `finish` organizes them."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "runs"
        cls.outputs_before = tree(ROOT / "outputs")
        n, cls.folder = new_run.create("abc", M, cls.root, claude=True)
        work = cls.folder / "_work" / "abc"
        text = (ROOT / "outputs" / "abc" / f"commentary_{M}.md").read_text(encoding="utf-8")      # read only
        (work / f"commentary_{M}.md").write_text(text, encoding="utf-8")
        (work / f"commentary_{M}_draft.md").write_text(text + "\n", encoding="utf-8")
        (work / f"commentary_grade_{M}.json").write_text(json.dumps({"retry_used": False, "attempts": [{"passed": True, "numbers": "1/1", "mismatches": []}]}))
        (work / f"commentary_final_grade_{M}.json").write_text(json.dumps({"passed": True, "numbers": "1/1", "mismatches": []}))
        (work / f"review_{M}_first.json").write_text(json.dumps({"verdict": "changes", "changes": []}))
        (work / f"review_{M}.json").write_text(json.dumps({"verdict": "approve", "open_questions": [{"question": "Q?"}]}))
        (work / f"monthly_review_{M}.xlsx").write_bytes(b"PK")
        (work / f"owner_memo_{M}.md").write_text("# memo\n", encoding="utf-8")
        cls.result = new_run.finalize(cls.folder)
        cls.outputs_after = tree(ROOT / "outputs")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_all_six_sections_are_filled_from_the_work_folder(self):
        f = self.folder
        for rel in (f"01_intake/intake_{M}.json", f"02_numbers/review_packet_{M}.json", f"03_commentary/commentary_{M}_draft.md",
                    f"03_commentary/commentary_{M}_final.md", f"03_commentary/commentary_grade_{M}.json", f"03_commentary/commentary_final_grade_{M}.json",
                    f"04_review/review_{M}_first.json", f"04_review/review_{M}_final.json", f"06_pack/monthly_review_{M}.xlsx",
                    f"06_pack/owner_memo_{M}.md", "05_evals/golden_results.txt", "05_evals/commentary_grade_report.txt",
                    "05_evals/flawed_control_check.txt", "05_evals/workbook_hash.txt", "05_evals/evals_summary.json", "SUMMARY.md"):
            self.assertTrue((f / rel).is_file(), rel)
        self.assertFalse((f / "_work").exists())
        self.assertFalse((f / "03_commentary" / "NOT_RUN.md").exists())

    def test_run_json_and_summary_carry_the_outcomes(self):
        r = self.result
        self.assertEqual((r["status"], r["kind"], r["reviewer_first_verdict"], r["reviewer_final_verdict"], r["open_question_count"]),
                         ("complete", "Full (Claude)", "changes", "approve", 1))
        summary = (self.folder / "SUMMARY.md").read_text(encoding="utf-8")
        for needle in ("changes → approve", "PASS", "Open questions", "Q?", "post-submission" if r["git_branch"] == "post-submission" else r["git_branch"]):
            self.assertIn(needle, summary)

    def test_flawed_control_must_fail_and_that_counts_as_a_pass(self):
        ev = json.loads((self.folder / "05_evals" / "evals_summary.json").read_text(encoding="utf-8"))
        self.assertIn("RESULT: FAIL", (self.folder / "05_evals" / "flawed_control_check.txt").read_text(encoding="utf-8"))
        self.assertEqual(ev["flawed_control"]["status"], "PASS")
        self.assertEqual(ev["workbook_hash"]["status"], "PASS")
        text = (self.folder / "05_evals" / "commentary_grade_report.txt").read_text(encoding="utf-8")
        self.assertEqual(ev["commentary_grade"]["status"], "PASS" if "RESULT: PASS" in text else "FAIL")

    def test_nothing_is_written_to_outputs(self):
        self.assertEqual(self.outputs_before, self.outputs_after)


class RegressFlag(unittest.TestCase):
    def test_regress_output_is_saved_and_outputs_regress_results_is_restored(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            results = t / "regress_results.json"
            results.write_text('{"original": true}', encoding="utf-8")
            stub = t / "stub_regress.py"
            stub.write_text(f"from pathlib import Path\nPath(r'{results}').write_text('{{\"changed\": true}}')\nprint('3/3 checks held')\n", encoding="utf-8")
            folder = t / "runs" / "run1"
            (folder / "05_evals").mkdir(parents=True)
            with mock.patch.object(new_run, "REGRESS", stub), mock.patch.object(new_run, "REGRESS_RESULTS", results):
                rec = new_run.run_regress(folder)
            self.assertEqual(results.read_text(encoding="utf-8"), '{"original": true}')
            saved = json.loads((folder / "05_evals" / "regress_fast.json").read_text(encoding="utf-8"))
            self.assertTrue(saved["held"] and rec["held"])
            self.assertIn("3/3 checks held", saved["output"])
            self.assertEqual(saved["results"], {"changed": True})


class RealRunsFolderIsUntouched(unittest.TestCase):
    def test_real_runs_folder_still_exists_with_its_readme_and_the_same_run_folders(self):
        self.assertTrue(REAL_RUNS.is_dir())
        self.assertTrue((REAL_RUNS / "README.md").is_file())
        self.assertEqual(sorted(p.name for p in REAL_RUNS.iterdir()), BEFORE_REAL)

    def test_no_test_or_script_deletes_a_run_folder(self):
        src = (ROOT / "scripts" / "new_run.py").read_text(encoding="utf-8")
        self.assertNotIn("rmtree(folder", src)
        self.assertNotRegex(src, r"rmtree\(\s*(?:root|RUNS)")


if __name__ == "__main__":
    unittest.main()
