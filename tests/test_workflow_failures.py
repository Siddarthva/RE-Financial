"""Workflow failure modes give one clear message, never a stack trace, and write nothing they should not
(Phase 3, 2026-10-14; see 04_architecture/workflows/). Real outputs/ is never written: every case uses a temp
root or refuses before writing."""
import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import client_sandbox  # noqa: E402
import monthly_review as mr  # noqa: E402


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def cli(*args):
    r = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    return r.returncode, (r.stdout + r.stderr)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def assertClean(self, code, out, want_code, phrase):
        self.assertEqual(code, want_code, out[-500:])
        self.assertNotIn("Traceback", out)
        self.assertIn(phrase, out)


class Pipeline(Base):  # workflow (a)
    def test_invalid_client_id_is_refused_before_any_path_is_built(self):
        out_root = self.tmp / "out"
        code, out = cli("scripts/run_pipeline.py", "../x", "2026-06", "--outputs-root", str(out_root))
        self.assertClean(code, out, 2, "invalid client id '../x'")
        self.assertFalse((self.tmp / "x").exists())
        self.assertFalse(out_root.exists())

    def test_bad_month_and_unknown_client(self):
        o = ["--outputs-root", str(self.tmp / "out")]
        self.assertClean(*cli("scripts/run_pipeline.py", "abc", "2026-13", *o), 2, "month must look like 2026-06")
        self.assertClean(*cli("scripts/run_pipeline.py", "nope", "2026-06", *o), 2, "unknown client 'nope'")

    def test_sandbox_rejects_traversal_client_ids(self):
        with self.assertRaisesRegex(ValueError, "Invalid client id"):
            with client_sandbox.client_sandbox("../x", self.tmp / "clients", self.tmp / "out"):
                pass
        self.assertFalse((self.tmp / "x").exists())


class SkillSteps(Base):  # workflow (b)
    def test_prepare_errors_are_one_line(self):
        self.assertClean(*cli("src/monthly_review.py", "prepare", "abc", "2026-13"), 1, "ERROR: Month must look like 2026-06")
        self.assertClean(*cli("src/monthly_review.py", "prepare", "nope", "2026-06"), 1, "ERROR: Unknown client 'nope'")
        self.assertClean(*cli("src/monthly_review.py", "prepare", "abc", "2024-01"), 1, "ERROR: Intake refused the workbook")

    def test_build_names_the_missing_or_broken_input(self):
        out = self.tmp / "out"
        (out / "abc").mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "Review packet not found.*prepare abc 2026-06"):
            mr.build("abc", "2026-06", self.tmp / "c.md", self.tmp / "r.json", outputs_root=out)
        (out / "abc" / "review_packet_2026-06.json").write_text("{}", encoding="utf-8")
        (self.tmp / "c.md").write_text("1. A statement.\n", encoding="utf-8")
        (self.tmp / "r.json").write_text("{not json", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Reviewer verdict is not valid JSON"):
            mr.build("abc", "2026-06", self.tmp / "c.md", self.tmp / "r.json", outputs_root=out)


class Approval(Base):  # workflow (c)
    def run_approve(self, *args):
        ap = load("approve_under_test", "scripts/approve.py")
        ap.OUT = self.tmp
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["approve.py", *args]), contextlib.redirect_stdout(buf):
            code = ap.main()
        return code, buf.getvalue()

    def test_damaged_decision_file_records_nothing(self):
        d = self.tmp / "abc"
        d.mkdir()
        (d / "review_packet_2026-06.json").write_text("{}", encoding="utf-8")
        (d / "approval_2026-06.json").write_text("{broken", encoding="utf-8")
        code, out = self.run_approve("abc", "2026-06", "--reviewer", "R", "--reason", "x", "--reject")
        self.assertClean(code, out, 5, "Nothing was recorded")
        self.assertFalse((d / "audit_log.jsonl").exists())

    def test_approved_period_is_locked(self):
        d = self.tmp / "abc"
        d.mkdir()
        (d / "review_packet_2026-06.json").write_text("{}", encoding="utf-8")
        (d / "approval_2026-06.json").write_text(json.dumps({"status": "approved"}), encoding="utf-8")
        code, out = self.run_approve("abc", "2026-06", "--reviewer", "R", "--reason", "x", "--reject")
        self.assertClean(code, out, 3, "approved and locked")


class Connection(Base):  # workflow (d)
    def test_invalid_client_and_missing_server(self):
        self.assertClean(*cli("01_connection/qbo_test_connection.py", "ABC", "--test"), 2, "invalid client id 'ABC'")
        qt = load("qbo_test_under_test", "01_connection/qbo_test_connection.py")
        qt.OUT, qt.SERVER = self.tmp, self.tmp / "no_server" / "dist" / "index.js"
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["qbo_test_connection.py", "abc", "--test"]), contextlib.redirect_stdout(buf):
            code = qt.main()
        self.assertEqual(code, 1)
        self.assertIn("was not found at", buf.getvalue())
        self.assertEqual(json.loads((self.tmp / "abc" / "qbo_status.json").read_text(encoding="utf-8"))["last_test"]["cause"], "server_missing")


class Loader(Base):  # workflow (e)
    def test_bad_dates_empty_range_and_bad_compare_file(self):
        self.assertClean(*cli("01_connection/load_workbook_to_sandbox.py", "--dry-run", "--from", "2026-13"), 2, "--from must look like 2026-06")
        self.assertClean(*cli("01_connection/load_workbook_to_sandbox.py", "--dry-run", "--from", "2026-06", "--to", "2026-01"), 2, "is after --to")
        bad = self.tmp / "bad.json"
        bad.write_text("{nope", encoding="utf-8")
        self.assertClean(*cli("01_connection/load_workbook_to_sandbox.py", "--compare", str(bad)), 1, "--compare file is not valid JSON")
        loader = load("loader_under_test", "01_connection/load_workbook_to_sandbox.py")
        with mock.patch.object(loader.run_client, "OUTPUTS_ROOT", self.tmp), self.assertRaisesRegex(SystemExit, "nothing was written"):
            loader.main(["--dry-run", "--from", "2027-01"])
        self.assertEqual(list(self.tmp.rglob("qbo_load_plan.json")), [])


class Packaging(Base):  # workflow (g)
    def test_no_git_gives_a_message_and_no_zip(self):
        pk = load("package_under_test", "scripts/package_submission.py")
        with mock.patch.object(pk.subprocess, "run", side_effect=OSError("git missing")), \
                self.assertRaisesRegex(SystemExit, "git is not installed"):
            pk.main(["--out", "dist/should_not_exist.zip"])
        self.assertFalse((ROOT / "dist" / "should_not_exist.zip").exists())

    def test_zip_outside_repo_is_refused(self):
        pk = load("package_under_test2", "scripts/package_submission.py")
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(pk.main(["--out", "../x.zip"]), 2)
        self.assertIn("outside the repo", buf.getvalue())


@unittest.skipUnless((ROOT / "05_review_workspace" / "app").is_dir(), "app/ not present in this copy")  # as in test_ui_numbers
class WorkspaceActions(unittest.TestCase):  # workflow (f)
    def test_timeout_is_reported_as_a_timeout(self):
        sys.path.insert(0, str(ROOT / "05_review_workspace" / "app"))
        actions = load("actions_under_test", "05_review_workspace/app/actions.py")
        with mock.patch.object(actions.subprocess, "run", side_effect=subprocess.TimeoutExpired("x", 1)):
            ok, text = actions.run_analysis("abc", "2026-06")
        self.assertFalse(ok)
        self.assertIn("did not finish within", text)


if __name__ == "__main__":
    unittest.main()
