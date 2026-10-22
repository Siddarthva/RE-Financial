"""Demo runs page (05_review_workspace/app/views/demo_run.py): the full review of the run chosen in the sidebar selector.

Uses small invented fixture runs in a temp folder, not model output. Checks one page per run (newest first), that every
section renders, that every $ / % / pp outside the verbatim commentary and the raw JSON exists in THAT run's packet,
the 'written by Claude, graded by code' label, the red banner on a failing grade, no engine imports, and empty states.
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
FORBIDDEN = {"abc_workbook_adapter", "financial_analysis", "monthly_review", "run_client", "close_artifacts",
             "client_sandbox", "openpyxl", "numpy", "scipy", "new_run", "commentary_retry"}

if APP.is_dir():
    sys.path.insert(0, str(APP))
    from streamlit.testing.v1 import AppTest
    import streamlit as st
    import actions
    import data
    import ui

TOKEN = {"money": re.compile(r"\$[\d,]+(?:\.\d+)?"), "pct": re.compile(r"\d+(?:\.\d+)?%"), "pp": re.compile(r"\d+(?:\.\d+)? pp")}
SECTIONS = ["1. Run summary", "2. Headline numbers", "3. Commentary review", "4. Grade history",
            "5. Reviewer scores and open questions", "6. Top movements and flux items", "7. Owner memo", "8. Raw files", "9. Excel pack"]
M = "2026-06"


def packet(rev, ni):
    line = lambda v, c, p: {"value": v, "mom_change": c, "mom_pct": p}  # noqa: E731
    return {"latest_month": M, "prior_month": "2026-05", "client": "abc", "months": {M: {
        "revenue": line(rev, -12452.8, -0.0598), "gross_profit": {"value": 137420.0, "margin": 0.701516, "margin_change_pp": -2.5},
        "operating_expenses": line(468200.5, 9100.25, 0.0198), "operating_income": line(ni, 8343.52, -0.0246),
        "net_income": line(ni, 8343.52, -0.0246)}},
        "cash": {"value": 713481.26, "mom_change": -215543.33, "mom_pct": -0.23201, "primary_window": "3m",
                 "runway_months": {"3m": 3.403094}},
        "line_items": {"Events & Conferences": {"value": 29294.58, "prior_value": 11323.91, "mom_change": 17970.67}},
        "top_movements": [{"account": "Events & Conferences", "mom_change": 17970.67}, {"account": "Bad Debts", "mom_change": -14741.53}]}


def make_run(root, n, *, grade_passed=True, drop=(), client="abc", rev=195898.16, ni=-330756.08):
    d = Path(root) / f"output_{n:03d}"
    out = d / client
    out.mkdir(parents=True)
    files = {
        f"review_packet_{M}.json": packet(rev, ni),
        f"review_{M}_first.json": {"verdict": "changes", "changes": [{"statement": 2, "type": "invented_cause", "issue": "cause not in packet"}],
                                   "statement_notes": [{"statement": 1, "status": "ok", "note": ""}]},
        f"review_{M}.json": {"verdict": "approve", "changes": [], "statement_notes": [{"statement": 2, "status": "ok", "note": "fixed"}],
                             "scores": {k: {"ok": 3, "of": 3} for k in ("numbers", "coverage", "causes", "tone")},
                             "open_questions": [{"question": "What drove Bad Debts?", "why": "large swing"}]},
        f"commentary_grade_{M}.json": {"retry_used": True, "attempts": [{"passed": False, "numbers": "1/2", "mismatches": ["Number 'x' matches nothing"]},
                                                                       {"passed": True, "numbers": "2/2", "mismatches": []}]},
        f"commentary_final_grade_{M}.json": {"passed": grade_passed, "numbers": "2/2" if grade_passed else "1/2",
                                             "mismatches": [] if grade_passed else ["Cash balance from the packet is not stated"]},
        f"flux_{M}.json": {"items": [{"account": "Events & Conferences", "section": "operating expenses", "reason_code": "LARGE_MOVE",
                                      "severity": "medium", "current": 29294.58, "prior": 11323.91, "dollar_change": 17970.67,
                                      "pct_change": -0.0598, "source_cell_current": "Income Statement!C65",
                                      "threshold_rule": "|$5,000| not in packet, raw only"}]},
    }
    for name, obj in files.items():
        if name not in drop:
            (out / name).write_text(json.dumps(obj), encoding="utf-8")
    if f"commentary_{M}.md" not in drop:
        (out / f"commentary_{M}.md").write_text(
            f"# ABC\n\n## Headline\n1. Revenue was $195,898.16, down 5.98% from 2026-05.\n2. Cash was $713,481.26 with 3.4 months of runway.\n", encoding="utf-8")
    if f"owner_memo_{M}.md" not in drop:
        (out / f"owner_memo_{M}.md").write_text(f"# Owner memo\n\nRevenue was ${rev:,.0f} in June.\n", encoding="utf-8")
    if f"monthly_review_{M}.xlsx" not in drop:
        (out / f"monthly_review_{M}.xlsx").write_bytes(b"PK-fixture")
    if "run.json" not in drop:
        (d / "run.json").write_text(json.dumps({
            "run_number": n, "run_id": d.name, "client": client, "month": M,
            "started": {"utc": "2026-10-22T05:48:45+00:00", "ist": "2026-10-22T11:18:45+05:30"},
            "finished": {"utc": "2026-10-22T05:50:00+00:00", "ist": "2026-10-22T11:20:00+05:30"},
            "git_branch": "post-submission", "git_head": "1b31efd" + "0" * 33, "workbook_sha256_16": "75da8d679a89551f",
            "stages": {"Intake": "done", "Calculate": "done", "Review": "done"},
            "grade_attempts": [{"attempt": 1, "passed": False, "numbers": "1/2", "mismatches": ["Number 'x' matches nothing"]},
                               {"attempt": 2, "passed": True, "numbers": "2/2", "mismatches": []}],
            "retry_used": True, "reviewer_first_verdict": "changes", "reviewer_final_verdict": "approve",
            "final_grade": {"passed": grade_passed, "numbers": "2/2" if grade_passed else "1/2",
                            "mismatches": [] if grade_passed else ["Cash balance from the packet is not stated"]},
            "pack_path": f"{client}/monthly_review_{M}.xlsx", "open_question_count": 1}), encoding="utf-8")
    return d


def make_pipeline_run(root, n, *, client="abc", rev=987654.32, ni=-888888.88, month=M, started="2026-10-22T07:00:00+00:00"):
    """What scripts/new_run.py leaves behind: packet, flux, tables, intake, manifest, audit log, run.json with the Claude stages 'not run'."""
    d = Path(root) / f"output_{n:03d}"
    out = d / client
    out.mkdir(parents=True)
    pk = packet(rev, ni)
    pk["latest_month"] = month
    pk["months"] = {month: pk["months"][M]}
    files = {f"review_packet_{month}.json": pk,
             f"flux_{month}.json": {"prior_period": "2026-05", "items": []},
             f"tables_{month}.json": {"months": [month], "revenue_by_stream": {"Subscriptions": {month: rev}},
                                      "opex_by_category": {"Events": {month: 29294.58}}},
             f"intake_{month}.json": {"status": "pass", "workbook": "ABC.xlsx", "sha256": "75da8d679a89551f" + "0" * 48,
                                      "sheets_detected": ["Income Statement"], "period_start": "2026-01", "period_end": month,
                                      "months": 6, "checks": [{"check": "BS balances", "passed": True, "cell_ref": "BS!B1"}]},
             f"manifest_20261022T070000Z-{client}-{month}.json": {"run_id": f"20261022T070000Z-{client}-{month}", "skill_version": "1",
                                                                  "source": {"sha256": "75da8d679a89551f" + "0" * 48}}}
    for name, obj in files.items():
        (out / name).write_text(json.dumps(obj), encoding="utf-8")
    (out / "audit_log.jsonl").write_text(json.dumps({"period": month, "event": "pipeline", "at": "2026-10-22"}) + "\n", encoding="utf-8")
    (d / "run.json").write_text(json.dumps({
        "run_number": n, "run_id": d.name, "client": client, "month": month,
        "started": {"utc": started, "ist": started}, "finished": {"utc": started, "ist": started},
        "git_branch": "post-submission", "git_head": "42bde44" + "0" * 33, "workbook_sha256_16": "75da8d679a89551f", "pipeline_status": "success",
        "stages": {"Intake": "done", "Calculate": "done", "Commentary draft": "not run", "Review": "not run", "Package": "not run"},
        "timings": {"Intake": {"started": started, "ended": started, "duration_s": 0.5, "status": "done"},
                    "Calculate": {"started": started, "ended": started, "duration_s": 3.7, "status": "done"}},
        "grade_attempts": None, "retry_used": None, "reviewer_first_verdict": None, "reviewer_final_verdict": None,
        "final_grade": None, "pack_path": None, "open_question_count": None}), encoding="utf-8")
    return d


def render_page(page, root, pick=None, claude="claude"):
    """One views/<page>.py rendered headless against a demo_runs folder at `root`; `pick` is the selected run folder name."""
    src = (f"import sys; sys.path.insert(0, r'{APP}')\nimport streamlit as st\nfrom views import {page} as v\n"
           + (f"st.session_state['run_pick'] = {pick!r}\n" if pick else "") + "v.render()\n")
    with mock.patch.object(data, "DEMO_RUNS", Path(root)), mock.patch.object(actions, "claude_path", return_value=claude):
        return AppTest.from_string(src, default_timeout=120).run()


def render(run_dir):
    return render_page("demo_run", Path(run_dir).parent, pick=Path(run_dir).name)


def shown(at, skip_statement_column=True):
    """Strings a user sees, except raw JSON expanders and the verbatim commentary column."""
    out = []

    def walk(block):
        for el in block.children.values():
            if el.type == "json":
                continue
            for attr in ("value", "body", "label", "delta", "help"):
                v = getattr(el, attr, None) if attr != "value" or el.type != "download_button" else None
                if isinstance(v, str):
                    out.append(v)
                elif hasattr(v, "columns"):
                    df = v.drop(columns=["Statement"], errors="ignore") if skip_statement_column else v
                    out.extend(map(str, df.columns))
                    out.extend(str(c) for c in df.to_numpy().ravel())
            if hasattr(el, "children"):
                walk(el)

    walk(at.main)
    return "\n".join(out)


def numbers_in(o):
    if isinstance(o, bool):
        return
    if isinstance(o, (int, float)):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from numbers_in(v)
    elif isinstance(o, list):
        for v in o:
            yield from numbers_in(v)


def allowed(run_dir, month=M, client="abc"):
    raw = json.loads((Path(run_dir) / client / f"review_packet_{month}.json").read_text(encoding="utf-8"))
    ok = {k: set() for k in TOKEN}
    for v in numbers_in(raw):
        for s in (ui.money(v), ui.money2(v), ui.pct(v), ui.pp(v) or ""):
            for k, rx in TOKEN.items():
                ok[k] |= set(rx.findall(s))
    return ok


@unittest.skipUnless(APP.is_dir(), "app/ not present in this copy")
class DemoRunPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.good = make_run(cls.root, 1)
        cls.bad = make_run(cls.root, 2, grade_passed=False, rev=111111.11, ni=-222222.22)
        cls.sparse = make_run(cls.root, 3, drop=(f"flux_{M}.json", f"monthly_review_{M}.xlsx", "run.json"))
        cls.page = {n: render(d) for n, d in (("good", cls.good), ("bad", cls.bad), ("sparse", cls.sparse))}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_sidebar_selector_lists_runs_newest_first_and_drives_the_page(self):
        with mock.patch.object(data, "DEMO_RUNS", self.root):
            at = AppTest.from_file(str(APP / "Home.py"), default_timeout=120).run()
            self.assertFalse(at.exception, [e.value for e in at.exception])
            sel = at.sidebar.selectbox[0]
            self.assertEqual(sel.label, "Run")
            self.assertEqual(list(sel.options), [
                "Output 003 · abc 2026-06 · Pipeline only · not graded",
                "Output 002 · abc 2026-06 · 11:18 IST · Full (Claude) · FAIL",
                "Output 001 · abc 2026-06 · 11:18 IST · Full (Claude) · PASS"])
            self.assertIn("Showing: Output 003", " ".join(m.value for m in at.markdown))
            at.sidebar.selectbox[0].select("Output 001 · abc 2026-06 · 11:18 IST · Full (Claude) · PASS").run()
        self.assertIn("Showing: Output 001", " ".join(m.value for m in at.markdown))
        self.assertIn("$195,898", shown(at))
        self.assertEqual(set(sec.label for sec in at.sidebar.selectbox), {"Run"})  # no Client / Period selectors

    def test_every_section_renders(self):
        at = self.page["good"]
        self.assertFalse(at.exception, [e.value for e in at.exception])
        headers = [h.value for h in at.header]
        self.assertEqual(headers, SECTIONS)
        text = shown(at)
        for needle in ("PASS", "post-submission", "75da8d679a89551f", "changes → approve", "Revenue", "Gross margin", "OPEX", "Net income",
                       "Cash", "Runway", "What drove Bad Debts?", "Events & Conferences", "changed in first review"):
            self.assertIn(needle, text)
        self.assertIn("Showing: Output 001 (", " ".join(m.value for m in at.markdown))
        self.assertEqual(len(at.get("download_button")), 1)
        self.assertEqual(len(at.expander), 7)
        self.assertEqual(len(at.get("json")), 7)  # packet, review, review_first, grade record, final grade, flux, run.json

    def test_numbers_shown_exist_in_that_runs_packet(self):
        for name, d in (("good", self.good), ("bad", self.bad)):
            ok = allowed(d)
            for kind, found in {k: set(rx.findall(shown(self.page[name]))) for k, rx in TOKEN.items()}.items():
                self.assertEqual(found - ok[kind], set(), f"{name}: {kind} not in this run's packet")
        # the runs differ, so a page can only pass by reading its own packet
        self.assertIn("$195,898", shown(self.page["good"]))
        self.assertNotIn("$195,898", shown(self.page["bad"]))
        self.assertIn("$111,111", shown(self.page["bad"]))

    def test_commentary_is_verbatim_and_labelled(self):
        at = self.page["good"]
        self.assertIn("written by claude, graded by code", shown(at).lower())
        df = next(d.value for d in at.dataframe if "Statement" in d.value.columns)
        self.assertEqual(list(df["Statement"]), ["Revenue was $195,898.16, down 5.98% from 2026-05.",
                                                 "Cash was $713,481.26 with 3.4 months of runway."])
        self.assertEqual(list(df["Flag"]), ["", "changed in first review"])

    def test_red_banner_only_on_failing_grade(self):
        self.assertEqual([e.value for e in self.page["bad"].error], ["Code grader failed: not ready for sign-off"])
        self.assertEqual(len(self.page["good"].error), 0)
        self.assertIn("FAIL", shown(self.page["bad"]))

    def test_missing_files_are_listed_not_fatal(self):
        at = self.page["sparse"]
        self.assertFalse(at.exception, [e.value for e in at.exception])
        warn = " ".join(w.value for w in at.warning)
        self.assertIn("Not produced in this run", warn)
        for name in ("run.json", f"flux_{M}.json", f"monthly_review_{M}.xlsx"):
            self.assertIn(name, warn)
            self.assertIn(f"Not produced in this run: {name}", " ".join(m.value for m in at.markdown).replace("<code>", "").replace("</code>", ""))
        self.assertEqual(len(at.get("download_button")), 0)
        self.assertEqual([h.value for h in at.header], SECTIONS)

    def test_no_page_imports_engine_modules(self):
        bad = []
        for f in APP.rglob("*.py"):
            for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                    [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                bad += [f"{f.name}: {n}" for n in names if n.split(".")[0] in FORBIDDEN]
        self.assertEqual(bad, [])

    def test_empty_state(self):
        with tempfile.TemporaryDirectory() as t:
            at = render_page("demo_run", Path(t) / "nope")
        self.assertFalse(at.exception)
        text = shown(at) + " ".join(m.value for m in at.markdown)
        self.assertIn("No runs yet. Click 'Run full analysis with Claude' or run /demo-run abc 2026-06", text)
        self.assertEqual(len(at.header), 0)


if __name__ == "__main__":
    unittest.main()
