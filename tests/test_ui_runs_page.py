"""Runs page (05_review_workspace/app/views/runs.py): one list of the run folders in demo_runs/, with everything for the selected run.

Uses invented fixture runs in a temp folder; no model is called. The Claude button's subprocess and the pipeline button's script are mocked.
Also covers scripts/new_run.py `mark` / `finish` (stage timings) and that no page imports engine modules.
"""
import ast
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "05_review_workspace" / "app"
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

if APP.is_dir():
    sys.path.insert(0, str(APP))
    from streamlit.testing.v1 import AppTest
    import actions
    import data
    from test_ui_runs import FORBIDDEN, M, SECTIONS, TOKEN, allowed, make_pipeline_run, make_run, packet, render_page, shown
import new_run

TIMINGS = {name: {"started": "2026-10-22T05:49:00+00:00", "ended": "2026-10-22T05:49:12+00:00", "duration_s": 12.5, "status": "done"}
           for name in ("Intake", "Calculate", "Skill draft", "Grade attempt 1", "Grade attempt 2", "Review (first)", "Revise",
                        "Review (final)", "Final grade", "Package")}


def build(tmp):
    demo = Path(tmp) / "demo_runs"
    one = make_run(demo, 1)
    two = make_run(demo, 2, rev=111111.11, ni=-222222.22)
    for d, started in ((one, "2026-10-22T05:48:45+00:00"), (two, "2026-10-22T06:30:00+00:00")):
        f = d / "run.json"
        r = json.loads(f.read_text(encoding="utf-8"))
        r["started"] = {"utc": started, "ist": started}
        r["timings"] = TIMINGS
        f.write_text(json.dumps(r), encoding="utf-8")
    pipe = make_pipeline_run(demo, 3)
    return demo, one, two, pipe


def runs_table(at):
    return next(d.value for d in at.dataframe if "Type" in d.value.columns)


class FakeProc:
    def __init__(self, lines=(), code=0, delay=0.0):
        import io
        import time
        self.pid, self.returncode, self._code = 1, None, code
        if delay:
            def slow():
                time.sleep(delay)
                yield from lines
            self.stdout = slow()
        else:
            self.stdout = io.StringIO("".join(lines))
        self.killed = False

    def wait(self, timeout=None):
        self.returncode = self._code
        return self._code

    def kill(self):
        self.killed = True


@unittest.skipUnless(APP.is_dir(), "app/ not present in this copy")
class RunsPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.demo, cls.one, cls.two, cls.pipe_dir = build(cls.tmp.name)
        cls.default = render_page("runs", cls.demo)  # newest run (the pipeline-only Output 003) is selected
        cls.full = render_page("runs", cls.demo, pick="output_001")
        cls.pipe = render_page("runs", cls.demo, pick="output_003")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_all_run_folders_listed_newest_first_and_nothing_else(self):
        df = runs_table(self.default)
        self.assertEqual(list(df.columns), ["Run", "Type", "Started (IST)", "Client", "Period", "Final grade", "Reviewer verdict", "Git SHA", "Status"])
        self.assertEqual(list(df["Run"]), ["Output 003", "Output 002", "Output 001"])
        self.assertEqual(list(df["Type"]), ["Pipeline only", "Full (Claude)", "Full (Claude)"])
        self.assertEqual(df.loc[1, "Final grade"], "PASS")
        self.assertEqual(df.loc[1, "Reviewer verdict"], "approve")
        self.assertEqual(df.loc[1, "Git SHA"], "1b31efd")
        self.assertEqual(df.loc[0, "Final grade"], "not run")

    def test_full_run_shows_everything(self):
        at = self.full
        self.assertFalse(at.exception, [e.value for e in at.exception])
        self.assertEqual([h.value for h in at.header], SECTIONS)
        text = shown(at)
        self.assertIn("written by claude, graded by code", text.lower())
        df = next(d.value for d in at.dataframe if "Statement" in d.value.columns)
        self.assertEqual(list(df["Flag"]), ["", "changed in first review"])
        self.assertEqual(len(at.get("json")), 7)  # packet, both reviews, grade record, final grade, flux, run.json
        self.assertEqual(len(at.get("download_button")), 1)
        self.assertIn("PASS", text)
        self.assertEqual(len(at.error), 0)
        self.assertEqual(len(at.warning), 0)

    def test_full_run_timeline_has_every_stage_with_status_and_duration(self):
        tl = next(d.value for d in self.full.dataframe if "Duration" in d.value.columns)
        self.assertEqual(list(tl["Stage"]), ["Intake", "Calculate", "Skill draft", "Grade attempt 1", "Grade attempt 2",
                                             "Review (first)", "Revise", "Review (final)", "Final grade", "Package"])
        self.assertEqual(set(tl["Duration"]), {"12.5s"})
        self.assertEqual(set(tl["Status"]), {"done"})

    def test_failing_final_grade_shows_red_banner(self):
        with tempfile.TemporaryDirectory() as t:
            make_run(Path(t), 9, grade_passed=False)
            at = render_page("runs", t, pick="output_009")
        self.assertEqual([e.value for e in at.error], ["Code grader failed: not ready for sign-off"])

    def test_pipeline_only_run_has_note_not_run_stages_packet_and_no_commentary(self):
        at = self.pipe
        self.assertFalse(at.exception, [e.value for e in at.exception])
        self.assertIn("Claude stages were not run for this run. Use 'Run full analysis with Claude' or /demo-run.",
                      [w.value for w in at.warning])
        tl = next(d.value for d in at.dataframe if "Duration" in d.value.columns)
        status = dict(zip(tl["Stage"], tl["Status"]))
        self.assertEqual(status["Intake"], "done")
        for stage in data.CLAUDE_STAGES:
            self.assertEqual(status[stage], "not run", stage)
        self.assertEqual(dict(zip(tl["Stage"], tl["Duration"]))["Calculate"], "3.7s")
        self.assertEqual(len(at.get("json")), 1)  # the run's own packet
        self.assertEqual(json.loads(at.get("json")[0].value)["months"][M]["revenue"]["value"], 987654.32)
        everything = shown(at) + " ".join(d.value.to_string() for d in at.dataframe)
        self.assertNotIn("Revenue was $195,898.16", everything)
        self.assertFalse([h for h in at.header if h.value == "3. Commentary review"])
        self.assertEqual(len(at.get("download_button")), 0)

    def test_every_amount_shown_exists_in_that_runs_packet(self):
        for at, d in ((self.full, self.one), (render_page("runs", self.demo, pick="output_002"), self.two)):
            ok = allowed(d)
            for kind, found in {k: set(rx.findall(shown(at))) for k, rx in TOKEN.items()}.items():
                self.assertEqual(found - ok[kind], set(), f"{kind} not in this run's packet")
        self.assertIn("$111,111", shown(render_page("runs", self.demo, pick="output_002")))

    def test_buttons_and_hint(self):
        labels = [b.label for b in self.default.button]
        self.assertEqual(labels, ["Run pipeline only (no Claude)", "Run full analysis with Claude"])
        at = render_page("runs", self.demo, claude=None)
        self.assertEqual([b.label for b in at.button], ["Run pipeline only (no Claude)"])
        self.assertIn("/demo-run", " ".join(c.value for c in at.caption))

    def test_pipeline_button_calls_new_run_and_selects_the_new_folder(self):
        with mock.patch.object(actions.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="C:\\x\\demo_runs\\output_004\n", stderr="")
            at = render_page("runs", self.demo)
            with mock.patch.object(data, "DEMO_RUNS", self.demo), mock.patch.object(actions, "claude_path", return_value="claude"):
                next(b for b in at.button if b.label == "Run pipeline only (no Claude)").click()
                at.run()
        args = run.call_args.args[0]
        self.assertEqual(args[1:], ["scripts/new_run.py", "abc", M])
        self.assertEqual(at.session_state["run_pick_next"], "output_004")

    def test_claude_button_runs_mocked_subprocess_and_selects_new_run(self):
        with tempfile.TemporaryDirectory() as t:
            demo = Path(t)
            make_run(demo, 1)

            def fake_popen(cmd, **kw):
                make_run(demo, 2)  # what /demo-run would leave behind
                return FakeProc(["working\n", "done\n"])

            with mock.patch.object(actions.subprocess, "Popen", side_effect=fake_popen) as popen:
                at = render_page("runs", demo)
                with mock.patch.object(data, "DEMO_RUNS", demo), mock.patch.object(actions, "claude_path", return_value="claude"):
                    next(b for b in at.button if b.label == "Run full analysis with Claude").click()
                    at.run()
            popen.assert_called_once()
            self.assertEqual(at.session_state["run_pick_next"], "output_002")


class ClaudeCommand(unittest.TestCase):
    def test_exact_command_and_no_bypass(self):
        md = (ROOT / ".claude" / "commands" / "demo-run.md").read_text(encoding="utf-8")
        tools = re.search(r"^allowed-tools: (.+)$", md, re.M).group(1).strip()
        self.assertEqual(actions.claude_command("abc", "2026-06"), ["claude", "-p", "/demo-run abc 2026-06", "--allowedTools", tools])
        joined = " ".join(actions.claude_command("abc", "2026-06"))
        for bad in ("dangerously", "bypass", "skip-permissions", "approve.py"):
            self.assertNotIn(bad, joined)

    def test_rejects_unsafe_arguments(self):
        for client, period in (("abc; rm -rf", "2026-06"), ("abc", "2026-13"), ("", "2026-06"), ("abc", "June")):
            with self.assertRaises(ValueError):
                actions.claude_command(client, period)

    def run_with(self, proc, **kw):
        with mock.patch.object(actions, "claude_path", return_value="claude"), \
                mock.patch.object(actions.subprocess, "Popen", return_value=proc) as popen, \
                mock.patch.object(actions, "_kill") as kill:
            return actions.run_claude("abc", "2026-06", **kw), popen, kill

    def test_success_failure_timeout_and_missing_cli(self):
        (status, log), popen, _ = self.run_with(FakeProc(["a\n", "b\n"]))
        self.assertEqual((status, log), ("ok", "a\nb\n"))
        self.assertEqual(popen.call_args.kwargs["cwd"], actions.PROJECT)
        self.assertNotIn("shell", popen.call_args.kwargs)
        self.assertEqual(self.run_with(FakeProc(["boom\n"], code=1))[0][0], "failed")
        (status, _), _, kill = self.run_with(FakeProc(["late\n"], delay=3), timeout=0.5)
        self.assertEqual(status, "timeout")
        kill.assert_called_once()
        with mock.patch.object(actions, "claude_path", return_value=None):
            self.assertEqual(actions.run_claude("abc", "2026-06")[0], "error")
        with mock.patch.object(actions, "claude_path", return_value="claude"), \
                mock.patch.object(actions.subprocess, "Popen", side_effect=OSError("nope")):
            self.assertEqual(actions.run_claude("abc", "2026-06")[0], "error")


class StageTimings(unittest.TestCase):
    def test_mark_records_start_end_duration_and_rejects_bad_input(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t)
            (f / "run.json").write_text(json.dumps({"client": "abc", "month": M, "stages": {}}), encoding="utf-8")
            new_run.mark(f, "Skill draft", "start")
            e = new_run.mark(f, "Skill draft", "end")
            self.assertEqual(e["status"], "done")
            self.assertIsInstance(e["duration_s"], float)
            new_run.mark(f, "Grade attempt 2", "start")
            self.assertEqual(new_run.mark(f, "Grade attempt 2", "end", "refused")["status"], "refused")
            self.assertEqual(new_run.mark(f, "Revise", "skipped")["duration_s"], 0.0)
            for stage, event in (("Nonsense", "start"), ("Package", "end"), ("Package", "pause")):
                with self.assertRaises(ValueError):
                    new_run.mark(f, stage, event)
            self.assertEqual(sorted(json.loads((f / "run.json").read_text(encoding="utf-8"))["timings"]),
                             ["Grade attempt 2", "Revise", "Skill draft"])

    def test_finish_sets_outcomes_and_skips_unneeded_revision(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t)
            out = f / "abc"
            out.mkdir()
            (f / "run.json").write_text(json.dumps({"client": "abc", "month": M, "stages": {}}), encoding="utf-8")
            (out / f"commentary_grade_{M}.json").write_text(json.dumps({"retry_used": False, "attempts": [{"passed": True, "numbers": "2/2", "mismatches": []}]}))
            (out / f"commentary_final_grade_{M}.json").write_text(json.dumps({"passed": True, "numbers": "2/2", "mismatches": []}))
            (out / f"review_{M}_first.json").write_text(json.dumps({"verdict": "approve"}))
            (out / f"review_{M}.json").write_text(json.dumps({"verdict": "approve"}))
            for s in ("Grade attempt 1", "Final grade", "Review (first)"):
                new_run.mark(f, s, "start")
                new_run.mark(f, s, "end")
            tm = new_run.finish(f)["timings"]
            self.assertEqual([tm[k]["status"] for k in ("Grade attempt 1", "Final grade", "Review (first)")], ["PASS", "PASS", "approve"])
            self.assertTrue(tm["Revise"]["status"].startswith("skipped"))


class NoEngineImports(unittest.TestCase):
    @unittest.skipUnless(APP.is_dir(), "app/ not present in this copy")
    def test_no_page_imports_engine_modules(self):
        bad = []
        for f in APP.rglob("*.py"):
            for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                    [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                bad += [f"{f.name}: {n}" for n in names if n.split(".")[0] in FORBIDDEN]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
