"""Runs page (05_review_workspace/app/views/runs.py): one list of Full (Claude) and Pipeline only runs, with everything for the selected run.

Uses invented fixture runs in a temp folder; no model is called. The Claude button's subprocess is mocked.
Also covers scripts/new_run.py `mark` (stage timings) and that no page imports engine modules.
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
    from test_ui_runs import FORBIDDEN, M, SECTIONS, TOKEN, allowed, make_run, packet, shown
import new_run

PIPE_NEW, PIPE_OLD = "20261022T070000Z-abc-2026-06", "20261014T073738Z-abc-2026-06"
PIPE_ONLY_COMMENTARY = "Pipeline-only commentary must never be shown on the Runs page."
TIMINGS = {name: {"started": "2026-10-22T05:49:00+00:00", "ended": "2026-10-22T05:49:12+00:00", "duration_s": 12.5, "status": "done"}
           for name in ("Intake", "Calculate", "Skill draft", "Grade attempt 1", "Grade attempt 2", "Review (first)", "Revise",
                        "Review (final)", "Final grade", "Package")}


def manifest(run_id, started):
    return {"run_id": run_id, "period": M, "started_at": started, "git_sha": "42bde44", "status": "success",
            "source": {"workbook": "ABC.xlsx"}, "skill_version": "1",
            "stages": [{"name": "Intake", "status": "done", "duration_s": 0.5}, {"name": "Calculate", "status": "done", "duration_s": 3.7}]}


def build(tmp):
    demo, outputs = Path(tmp) / "demo_runs", Path(tmp) / "outputs"
    one = make_run(demo, 1)
    two = make_run(demo, 2, rev=111111.11, ni=-222222.22)
    for d, started in ((one, "2026-10-22T05:48:45+00:00"), (two, "2026-10-22T06:30:00+00:00")):
        f = d / "run.json"
        r = json.loads(f.read_text(encoding="utf-8"))
        r["started"] = {"utc": started, "ist": started}
        r["timings"] = TIMINGS
        f.write_text(json.dumps(r), encoding="utf-8")
    out = outputs / "abc"
    out.mkdir(parents=True)
    for rid, started in ((PIPE_NEW, "2026-10-22T07:00:00+00:00"), (PIPE_OLD, "2026-10-14T07:37:38+00:00")):
        (out / f"manifest_{rid}.json").write_text(json.dumps(manifest(rid, started)), encoding="utf-8")
    (out / f"review_packet_{M}.json").write_text(json.dumps(packet(999999.99, -888888.88)), encoding="utf-8")
    (out / f"commentary_{M}.md").write_text(f"## Headline\n1. {PIPE_ONLY_COMMENTARY}\n", encoding="utf-8")
    return demo, outputs, one, two


def render_page(demo, outputs, pick=None, claude="claude"):
    src = (f"import sys; sys.path.insert(0, r'{APP}')\nimport streamlit as st\nfrom views import runs\n"
           f"st.session_state['ctx'] = {{'client': 'abc', 'period': '{M}'}}\n"
           + (f"st.session_state.setdefault('run_pick', {pick!r})\n" if pick else "") + "runs.render()\n")
    with mock.patch.object(data, "DEMO_RUNS", demo), mock.patch.object(data, "OUTPUTS", outputs), \
            mock.patch.object(actions, "claude_path", return_value=claude):
        return AppTest.from_string(src, default_timeout=120).run()


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
        cls.demo, cls.outputs, cls.one, cls.two = build(cls.tmp.name)
        cls.default = render_page(cls.demo, cls.outputs)
        cls.full = render_page(cls.demo, cls.outputs, pick="demo:output_001")
        cls.pipe = render_page(cls.demo, cls.outputs, pick=f"pipe:{PIPE_NEW}")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_both_kinds_listed_newest_first(self):
        df = runs_table(self.default)
        self.assertEqual(list(df.columns), ["Run", "Type", "Started (IST)", "Period", "Final grade", "Reviewer verdict", "Git SHA", "Status"])
        self.assertEqual(list(df["Run"]), [PIPE_NEW, "Output 002", "Output 001", PIPE_OLD])
        self.assertEqual(list(df["Type"]), ["Pipeline only", "Full (Claude)", "Full (Claude)", "Pipeline only"])
        self.assertEqual(df.loc[1, "Final grade"], "PASS 2/2")
        self.assertEqual(df.loc[1, "Reviewer verdict"], "approve")
        self.assertEqual(df.loc[1, "Git SHA"], "1b31efd")

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
        d = make_run(self.demo, 9, grade_passed=False)
        at = render_page(self.demo, self.outputs, pick="demo:output_009")
        try:
            self.assertEqual([e.value for e in at.error], ["Code grader failed: not ready for sign-off"])
        finally:
            import shutil
            shutil.rmtree(d)

    def test_pipeline_only_run_has_note_timeline_packet_and_no_commentary(self):
        at = self.pipe
        self.assertFalse(at.exception, [e.value for e in at.exception])
        self.assertIn("Claude stages were not run for this run. Use 'Run full analysis with Claude' or /demo-run.",
                      [w.value for w in at.warning])
        tl = next(d.value for d in at.dataframe if "Duration" in d.value.columns)
        self.assertEqual(dict(zip(tl["Stage"], tl["Status"]))["Intake"], "done")
        self.assertEqual(dict(zip(tl["Stage"], tl["Status"]))["Skill draft"], "not run")
        self.assertEqual(dict(zip(tl["Stage"], tl["Duration"]))["Calculate"], "3.7s")
        self.assertEqual(len(at.get("json")), 1)  # the packet
        self.assertEqual(json.loads(at.get("json")[0].value)["months"][M]["revenue"]["value"], 999999.99)  # this period's packet
        everything = shown(at) + " ".join(d.value.to_string() for d in at.dataframe)
        self.assertNotIn(PIPE_ONLY_COMMENTARY, everything)
        self.assertNotIn("Revenue was $195,898.16", everything)
        self.assertFalse([h for h in at.header if h.value == "3. Commentary review"])
        self.assertEqual(len(at.get("download_button")), 0)

    def test_every_amount_shown_exists_in_that_runs_packet(self):
        for at, d in ((self.full, self.one), (render_page(self.demo, self.outputs, pick="demo:output_002"), self.two)):
            ok = allowed(d)
            for kind, found in {k: set(rx.findall(shown(at))) for k, rx in TOKEN.items()}.items():
                self.assertEqual(found - ok[kind], set(), f"{kind} not in this run's packet")
        self.assertIn("$111,111", shown(render_page(self.demo, self.outputs, pick="demo:output_002")))

    def test_buttons_and_hint(self):
        labels = [b.label for b in self.default.button]
        self.assertEqual(labels, ["Run pipeline only (no Claude)", "Run full analysis with Claude"])
        self.assertNotIn("Run analysis", labels)
        at = render_page(self.demo, self.outputs, claude=None)
        self.assertEqual([b.label for b in at.button], ["Run pipeline only (no Claude)"])
        self.assertIn("/demo-run", " ".join(c.value for c in at.caption))

    def test_claude_button_runs_mocked_subprocess_and_selects_new_run(self):
        def fake_popen(cmd, **kw):
            make_run(self.demo, 3)  # what /demo-run would leave behind
            (self.demo / "output_003" / "run.json").write_text(json.dumps({"client": "abc", "month": M, "started": {"utc": "2026-10-22T08:00:00+00:00"}}))
            return FakeProc(["working\n", "done\n"])

        try:
            with mock.patch.object(actions.subprocess, "Popen", side_effect=fake_popen) as popen:
                at = render_page(self.demo, self.outputs)
                next(b for b in at.button if b.label == "Run full analysis with Claude").click()
                with mock.patch.object(data, "DEMO_RUNS", self.demo), mock.patch.object(data, "OUTPUTS", self.outputs), \
                        mock.patch.object(actions, "claude_path", return_value="claude"):
                    at.run()
            popen.assert_called_once()
            self.assertEqual(at.session_state["run_pick"], "demo:output_003")
        finally:
            import shutil
            shutil.rmtree(self.demo / "output_003", ignore_errors=True)


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
