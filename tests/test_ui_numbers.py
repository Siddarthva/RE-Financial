# scan-secrets: allow-fake-fixtures  (CANARIES below are invented values, used to prove they are never displayed)
"""The workspace app displays what is inside the selected run folder (runs/runN/) and nothing else.

Uses invented fixture runs in a temp folder (never outputs/ or the real runs/). Runs every client-data page headless
(streamlit AppTest) and checks:
  1. FILE ACCESS: file opening is patched; opening any data file outside the selected run folder fails the test. The only
     exceptions are the project pages' declared files (Evaluations, Architecture & Security);
  2. with no runs folder (or an empty one) every client-data page shows only the empty state: no $, % or pp, plus the run buttons;
  3. with two runs holding different numbers each page shows only the selected run's numbers, and switching runs switches them all;
  4. a file the run lacks reads "Not produced in this run: <file>" and is never borrowed from another run;
  5. every $ / % / pp shown (outside the verbatim commentary and raw JSON) exists in that run's packet; key figures equal the packet;
  6. no page imports an engine module; no token, realm ID or .env-style content reaches any page; an approved run renders as locked;
  7. the project pages carry the "Project-level results, not from a run" banner with source file and date, in their own sidebar section.
All tests skip when app/ is absent (e.g. the mutation-test copy).
"""
import ast
import builtins
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
APP = next((p for p in (ROOT / "05_review_workspace" / "app",) if (p / "Home.py").is_file()), None)
CLIENT_PAGES = ["overview", "analysis", "insights", "datasources", "runs", "run_detail"]
FORBIDDEN = {"abc_workbook_adapter", "financial_analysis", "monthly_review", "run_client", "close_artifacts",
             "client_sandbox", "openpyxl", "numpy", "scipy"}
DATA_SUFFIXES = {".json", ".jsonl", ".md", ".xlsx", ".csv", ".txt", ".yaml", ".yml", ".xls"}
EMPTY = "No runs yet. Click 'Run full analysis with Claude' or run /demo-run abc 2026-06"

if APP:
    sys.path.insert(0, str(APP))
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.path.insert(0, str(ROOT / "tests"))
    from streamlit.testing.v1 import AppTest
    import streamlit as st
    import data
    import ui
    import scan_secrets
    from test_ui_runs import M, TOKEN, allowed, make_pipeline_run, make_run, render_page, shown

# Fake credentials that must never be displayed even if they land in a JSON file.
CANARIES = ["eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjYW5hcnkifQ.c2lnbmF0dXJlMTIz", "realmId=9130350000000001",
            "refresh_token: RT1-canary0123456789abcdefghijklmnop", "Bearer canarycanarycanarycanary0123"]


def enrich(d, *, approved=False, status=None):
    """Add the files the engine would have written next to the packet: tables, intake, flux (two items), manifest, audit log."""
    nums, intake_dir, pack_dir = Path(d) / "02_numbers", Path(d) / "01_intake", Path(d) / "06_pack"
    pk = json.loads((nums / f"review_packet_{M}.json").read_text(encoding="utf-8"))
    rev, ev = pk["months"][M]["revenue"]["value"], pk["line_items"]["Events & Conferences"]
    files = {
        f"tables_{M}.json": {"months": [M], "revenue_by_stream": {"Subscriptions": {M: rev}}, "opex_by_category": {"Events": {M: ev["value"]}}},
        f"intake_{M}.json": {"status": "pass", "workbook": "ABC.xlsx", "sha256": "75da8d679a89551f" + "0" * 48, "sheets_detected": ["Income Statement"],
                             "period_start": "2026-01", "period_end": M, "months": 6,
                             "checks": [{"check": "BS balances", "passed": True, "cell_ref": "BS!B1"}]},
        f"flux_{M}.json": {"prior_period": "2026-05", "items": [  # file order is NOT size order
            {"account": "Bad Debts", "section": "opex", "reason_code": "LARGE_MOVE", "severity": "low", "metric": "x",
             "current": ev["prior_value"], "prior": ev["value"], "dollar_change": -14741.53, "pct_change": -0.0246,
             "source_cell_current": "Income Statement!C9", "threshold_rule": "r"},
            {"account": "Events & Conferences", "section": "opex", "reason_code": "SIGN_FLIP", "severity": "high", "metric": "x",
             "current": ev["value"], "prior": ev["prior_value"], "dollar_change": 17970.67, "pct_change": -0.0598,
             "source_cell_current": "Income Statement!C65", "threshold_rule": "r"}]},
        f"manifest_20261022T070000Z-abc-{M}.json": {"run_id": f"20261022T070000Z-abc-{M}", "skill_version": "1"},
    }
    for name, obj in files.items():
        ((intake_dir if name.startswith("intake_") else nums) / name).write_text(json.dumps(obj), encoding="utf-8")
    (nums / "audit_log.jsonl").write_text(json.dumps({"period": M, "event": "pipeline", "at": "2026-10-22"}) + "\n", encoding="utf-8")
    if approved:
        (pack_dir / f"approval_{M}.json").write_text(json.dumps(
            {"status": "approved", "reviewer": "T. Reviewer", "reason": "ok", "decided_at": "2026-10-14T00:00:00+00:00"}), encoding="utf-8")
    if status:
        (nums / "qbo_status.json").write_text(json.dumps(status), encoding="utf-8")
    return d


class OpenSpy:
    """Records every path opened through open() / io.open() / Path.open / read_text / read_bytes while it is active."""

    def __enter__(self):
        self.opened = []

        def wrap(real):
            def f(file, *a, **k):
                if isinstance(file, (str, bytes, os.PathLike)):
                    try:
                        self.opened.append(Path(os.fsdecode(file)).resolve())
                    except OSError:
                        pass
                return real(file, *a, **k)
            return f

        self._patches = [mock.patch.object(builtins, "open", wrap(builtins.open)), mock.patch.object(io, "open", wrap(io.open))]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()


def under(p, folder):
    try:
        p.relative_to(Path(folder).resolve())
        return True
    except ValueError:
        return False


def stray(opened, run_dir, scratch, extra=()):
    """Data files opened that are neither inside the run folder nor a declared project file. Python/library files are ignored.
    The one other exception is the run index: the selector and the Runs table read each run's run.json, and only that file."""
    ok = {Path(p).resolve() for p in extra}
    index = lambda p: p.name == "run.json" and re.fullmatch(r"run\d+", p.parent.name)  # noqa: E731
    return sorted({str(p) for p in opened if p.suffix.lower() in DATA_SUFFIXES and (under(p, ROOT) or under(p, scratch))
                   and not (run_dir is not None and under(p, run_dir)) and p not in ok and not index(p)})


def collect(at):
    """Every string a user could see (raw JSON expanders included): labels, values, deltas, dataframe headers and cells."""
    out = []

    def add(v):
        if isinstance(v, str):
            out.append(v)
        elif hasattr(v, "columns"):
            out.extend(map(str, v.columns))
            out.extend(str(c) for c in v.to_numpy().ravel())
        elif isinstance(v, (dict, list)):
            out.append(json.dumps(v))

    def walk(block):
        for el in block.children.values():
            for attr in ("value", "body", "label", "delta", "help"):
                try:
                    add(getattr(el, attr))
                except Exception:
                    continue
            if hasattr(el, "children"):
                walk(el)

    walk(at.main)
    return "\n".join(out)


def tokens(text):
    return {kind: set(rx.findall(text)) for kind, rx in TOKEN.items()}


def without_commentary(text, run_dir):
    """The commentary is Claude's verbatim text; every other string on the page is checked against the packet."""
    f = Path(run_dir) / "03_commentary" / f"commentary_{M}_final.md"
    lines = set(f.read_text(encoding="utf-8").splitlines()) if f.is_file() else set()
    return "\n".join(ln for ln in text.replace("\\$", "$").splitlines() if ln.strip() not in lines)


def page_text(at, run_dir):
    return without_commentary(shown(at), run_dir)


@unittest.skipUnless(APP, "app/ not present in this copy")
class NoCalculationImports(unittest.TestCase):
    def test_no_page_imports_a_calculation_module(self):
        bad = []
        for f in APP.rglob("*.py"):
            for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                    [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                bad += [f"{f.name}: {n}" for n in names if n.split(".")[0] in FORBIDDEN]
        self.assertEqual(bad, [])

    def test_clean_interpreter_loads_every_page_without_calculation_modules(self):
        code = (f"import sys; sys.path.insert(0, r'{APP}')\nimport data, ui, actions\n"
                "from views import analysis, architecture, datasources, run_detail, evaluations, insights, overview, run_controls, runs\n"
                f"print([m for m in {sorted(FORBIDDEN - {'numpy', 'scipy'})!r} if m in sys.modules])")  # pandas itself loads numpy
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=tempfile.gettempdir())
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertEqual(r.stdout.strip(), "[]")

    def test_only_the_data_layer_names_the_outputs_folder_and_no_sample_outputs_anywhere(self):
        for f in APP.rglob("*.py"):
            text = f.read_text(encoding="utf-8")
            self.assertNotIn("sample_outputs", text, f.name)
            if f.name not in ("data.py", "paths.py"):
                self.assertNotIn("OUTPUTS", text, f.name)
        views = "".join(f.read_text(encoding="utf-8") for f in (APP / "views").glob("*.py") if f.name not in ("evaluations.py", "architecture.py"))
        self.assertNotRegex(views, r"outputs/(?:<|\{)")  # no outputs/<client>/ paths in client-data pages

    def test_a_run_refuses_paths_outside_its_folder(self):
        with tempfile.TemporaryDirectory() as t:
            a, b = make_run(Path(t), 1), make_run(Path(t), 2)
            run = data.Run(a)
            with self.assertRaises(ValueError):
                run._path(f"../{b.name}/02_numbers/review_packet_{M}.json")


@unittest.skipUnless(APP, "app/ not present in this copy")
class RunOnlyDisplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.scratch = Path(cls.tmp.name).resolve()
        cls.root = cls.scratch / "runs"
        cls.a = enrich(make_run(cls.root, 1), approved=False)
        cls.b = enrich(make_run(cls.root, 2, rev=111111.11, ni=-222222.22))
        cls.c = make_pipeline_run(cls.root, 3)
        cls.at, cls.opened = {}, {}
        for run in (cls.a, cls.b, cls.c):
            for page in CLIENT_PAGES:
                with OpenSpy() as spy:
                    cls.at[page, run.name] = render_page(page, cls.root, pick=run.name)
                cls.opened[page, run.name] = spy.opened

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def runs(self):
        return {"run1": self.a, "run2": self.b, "run3": self.c}.items()

    # 1. file access ---------------------------------------------------------------------------------------------
    def test_no_page_opens_a_file_outside_the_selected_run_folder(self):
        for (page, name), opened in self.opened.items():
            run_dir = self.root / name
            self.assertEqual(stray(opened, run_dir, self.scratch), [], f"{page}/{name}")
            self.assertTrue([p for p in opened if under(p, run_dir)], f"{page}/{name}: expected to read the run folder")

    def test_the_guard_would_catch_a_borrowed_file(self):
        with OpenSpy() as spy:
            (self.b / "02_numbers" / f"review_packet_{M}.json").read_bytes()  # a page reading another run's file
        self.assertEqual(len(stray(spy.opened, self.a, self.scratch)), 1)

    def test_pages_render_and_name_the_run_they_show(self):
        for (page, name), at in self.at.items():
            self.assertEqual([e.value for e in at.exception], [], f"{page}/{name}")
            self.assertIn(f"Showing: Run {name[3:]} (", " ".join(m.value for m in at.markdown), f"{page}/{name}")

    # 3. each page shows only the selected run's numbers, and switching switches them -----------------------------
    def test_switching_runs_switches_every_number(self):
        for page in ("overview", "analysis", "runs", "run_detail"):
            one, two = page_text(self.at[page, "run1"], self.a), page_text(self.at[page, "run2"], self.b)
            self.assertIn("$195,898", one, page)
            self.assertNotIn("$111,111", one, page)
            self.assertIn("$111,111", two, page)
            self.assertNotIn("$195,898", two, page)
            self.assertNotIn("$987,654", one + two, page)  # the pipeline-only run's packet
        for page in ("overview", "analysis", "run_detail"):
            three = page_text(self.at[page, "run3"], self.c)
            self.assertIn("$987,654", three, page)
            self.assertNotIn("$195,898", three, page)
            self.assertNotIn("$111,111", three, page)

    def test_sidebar_selector_is_the_only_selector_and_drives_the_page(self):
        with mock.patch.object(data, "RUNS", self.root):
            at = AppTest.from_file(str(APP / "Home.py"), default_timeout=120).run()
            self.assertEqual([e.value for e in at.exception], [])
            self.assertEqual([s.label for s in at.sidebar.selectbox], ["Run"])
            self.assertEqual(len(at.sidebar.text_input), 0)
            options = list(at.sidebar.selectbox[0].options)
            self.assertEqual([o.split(" · ")[0] for o in options], ["Run 3", "Run 2", "Run 1"])
            at.sidebar.selectbox[0].select(options[2]).run()
            self.assertIn("Showing: Run 1", " ".join(m.value for m in at.markdown))
            self.assertIn("$195,898", shown(at))
            at.sidebar.selectbox[0].select(options[1]).run()
            self.assertIn("Showing: Run 2", " ".join(m.value for m in at.markdown))
            self.assertIn("$111,111", shown(at))
            self.assertNotIn("$195,898", without_commentary(shown(at), self.b))

    def test_navigation_separates_run_pages_from_project_pages(self):
        seen = {}
        real = st.navigation

        def spy(pages, *a, **k):
            seen.update({sec: [p.title for p in ps] for sec, ps in pages.items()})
            return real(pages, *a, **k)

        with mock.patch.object(data, "RUNS", self.root), mock.patch.object(st, "navigation", side_effect=spy):
            AppTest.from_file(str(APP / "Home.py"), default_timeout=120).run()
        self.assertEqual(seen, {"Run data": ["Overview", "Financial Analysis", "Insights & Review", "Data Sources", "Runs", "Run detail"],
                                "Project (not run data)": ["Evaluations", "Architecture & Security"]})

    # 4. missing means missing ------------------------------------------------------------------------------------
    def test_files_the_run_lacks_say_not_produced_and_are_never_borrowed(self):
        c = {page: collect(self.at[page, "run3"]).replace("<code>", "").replace("</code>", "") for page in CLIENT_PAGES}
        self.assertIn(f"Not produced in this run: 03_commentary/commentary_{M}_final.md", c["overview"])
        self.assertIn(f"Not produced in this run: 04_review/review_{M}_final.json", c["insights"])
        self.assertIn(f"Not produced in this run: 06_pack/approval_{M}.json", c["insights"])
        self.assertIn("Not produced in this run: 02_numbers/qbo_status.json", c["datasources"])
        self.assertIn(f"Not produced in this run: 06_pack/monthly_review_{M}.xlsx", c["analysis"])
        for needle in ("What drove Bad Debts?", "Revenue was $195,898.16", "$195,898", "$111,111"):
            self.assertFalse([p for p in CLIENT_PAGES if needle in c[p]], needle)
        a = {page: collect(self.at[page, "run1"]).replace("<code>", "").replace("</code>", "") for page in CLIENT_PAGES}
        self.assertIn("Not produced in this run: 02_numbers/qbo_status.json", a["datasources"])  # even though other files exist
        self.assertNotIn("Not produced in this run: commentary", a["overview"])

    def test_every_number_table_and_text_block_names_its_source_file(self):
        for name, run in self.runs():
            if run is self.c:
                continue
            for page in ("overview", "analysis", "insights", "run_detail"):
                notes = " ".join(m.value for m in self.at[page, name].markdown)
                self.assertIn(f"from <code>{name}/02_numbers/review_packet_{M}.json</code>" if page != "insights" else f"from <code>{name}/02_numbers/flux_{M}.json</code>",
                              notes, f"{page}/{name}")
        notes = " ".join(m.value for m in self.at["overview", "run1"].markdown)
        self.assertIn(f"from <code>run1/03_commentary/commentary_{M}_final.md</code>", notes)
        self.assertIn(f"from <code>run1/01_intake/intake_{M}.json</code>", notes)

    # 5. numbers --------------------------------------------------------------------------------------------------
    def test_every_displayed_amount_and_percentage_exists_in_that_runs_packet(self):
        for (page, name), at in self.at.items():
            run_dir = self.root / name
            ok = allowed(run_dir)
            for kind, vals in tokens(page_text(at, run_dir)).items():
                self.assertEqual(vals - ok[kind], set(), f"{page}/{name}: {kind} not in this run's packet")

    def test_overview_key_figures_equal_the_packet(self):
        for name, run in self.runs():
            if run is self.c:
                continue
            pk = json.loads((run / "02_numbers" / f"review_packet_{M}.json").read_text(encoding="utf-8"))
            m = pk["months"][M]
            metrics = {x.label: x for x in self.at["overview", name].metric}
            rev = m["revenue"]
            self.assertEqual(metrics["Revenue"].value, ui.money(rev["value"]))
            self.assertEqual(metrics["Revenue"].delta, ui.delta(rev.get("mom_change"), rev.get("mom_pct")))
            self.assertEqual(metrics["Gross margin"].value, ui.pct(m["gross_profit"]["margin"]))
            self.assertEqual(metrics["Operating expenses"].value, ui.money(m["operating_expenses"]["value"]))
            self.assertEqual(metrics["Net income"].value, ui.money(m["net_income"]["value"]))
            self.assertEqual(metrics["Cash"].value, ui.money(pk["cash"]["value"]))
            self.assertEqual(metrics["Runway (3m burn)"].value, f"{pk['cash']['runway_months']['3m']:.1f} months")

    def test_tables_ttm_and_flux_come_from_the_run_files(self):
        at = self.at["analysis", "run2"]
        streams = next(d.value for d in at.dataframe if "Item" in d.value.columns and "Subscriptions" in set(d.value["Item"]))
        self.assertEqual(list(streams[M]), ["$111,111"])
        ttm = next(d.value for d in at.dataframe if "Month" in d.value.columns and not any("Δ" in c or "margin" in c.lower() for c in d.value.columns))
        self.assertEqual(set(ttm["Revenue"]), {"not available"})
        at = self.at["insights", "run1"]
        table = next(d.value for d in at.dataframe if "Severity" in d.value.columns)
        self.assertEqual(list(table["Account"]), ["Events & Conferences", "Bad Debts"])  # sorted by absolute $ change, not file order
        self.assertEqual(list(table["Severity"]), ["High", "Low"])

    def test_reviewer_explanations_are_not_shown(self):
        text = collect(self.at["insights", "run1"])
        self.assertIn("What drove Bad Debts?", text)
        self.assertNotIn("large swing", text)

    def test_no_secrets_in_any_rendered_page(self):
        for (page, name), at in self.at.items():
            text = collect(at)
            hits = [(n, k) for n, k in scan_secrets.scan_text(text) if k not in scan_secrets.INFO_ONLY]
            self.assertEqual(hits, [], f"{page}/{name}")
            self.assertIsNone(re.search(r"(?m)^[A-Z][A-Z0-9_]{3,}=\S", text), f"{page}/{name}: env-style line")

    # 6. edge cases -----------------------------------------------------------------------------------------------
    def test_unreadable_json_shows_a_message_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as t:
            d = enrich(make_run(Path(t), 1))
            (d / "02_numbers" / f"review_packet_{M}.json").write_text("{not json", encoding="utf-8")
            at = render_page("overview", t, pick="run1")
        self.assertEqual([e.value for e in at.exception], [])
        self.assertIn(f"Could not read 02_numbers/review_packet_{M}.json", collect(at).replace("<code>", "").replace("</code>", ""))

    def test_credentials_in_a_run_file_are_withheld(self):
        status = {"method": "x", "flags": {}, "last_successful_retrieval": "2026-10-12",
                  "last_test": {"tested_at": "t", "ok": False, "message": " | ".join(CANARIES)}}
        with tempfile.TemporaryDirectory() as t:
            enrich(make_run(Path(t), 1), status=status)
            text = collect(render_page("datasources", t, pick="run1"))
        for c in CANARIES:
            self.assertNotIn(c, text)
            self.assertNotIn(c.split(":")[-1].split("=")[-1].strip(), text)
        self.assertIn("[withheld]", text)

    def test_approved_run_renders_as_locked_and_has_no_decision_form(self):
        with tempfile.TemporaryDirectory() as t:
            enrich(make_run(Path(t), 1), approved=True)
            for page in ("insights", "overview", "analysis"):
                at = render_page(page, t, pick="run1")
                self.assertEqual([e.value for e in at.exception], [], page)
                self.assertIn("Locked - approved", collect(at), page)
                self.assertNotIn("Approve", [b.label for b in at.button])
                self.assertNotIn("Reject", [b.label for b in at.button])


@unittest.skipUnless(APP, "app/ not present in this copy")
class EmptyState(unittest.TestCase):
    def test_no_runs_folder_shows_only_the_empty_state_and_the_run_buttons(self):
        with tempfile.TemporaryDirectory() as t:
            for root in (Path(t) / "missing", Path(t)):  # absent, then present but empty
                for page in CLIENT_PAGES:
                    at = render_page(page, root)
                    self.assertEqual([e.value for e in at.exception], [], page)
                    text = collect(at)
                    self.assertIn(EMPTY, text, page)
                    self.assertIsNone(re.search(r"[$%]|\bpp\b", text), f"{page}: a number-like symbol on the empty state")
                    self.assertEqual(len(at.metric), 0, page)
                    self.assertEqual(len(at.dataframe), 0, page)
                    self.assertEqual(len(at.get("json")), 0, page)
                    self.assertEqual(len(at.tabs), 0, page)
                    self.assertEqual([b.label for b in at.button], ["Run pipeline only (no Claude)", "Run full analysis with Claude"], page)

    def test_empty_state_opens_no_data_file(self):
        with tempfile.TemporaryDirectory() as t:
            scratch = Path(t).resolve()
            for page in CLIENT_PAGES:
                with OpenSpy() as spy:
                    render_page(page, scratch / "nothing")
                self.assertEqual(stray(spy.opened, None, scratch), [], page)

    def test_sidebar_has_no_selectors_without_runs(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(data, "RUNS", Path(t) / "none"):
            at = AppTest.from_file(str(APP / "Home.py"), default_timeout=120).run()
        self.assertEqual([e.value for e in at.exception], [])
        self.assertEqual(len(at.sidebar.selectbox), 0)
        self.assertIn("No runs yet", " ".join(c.value for c in at.sidebar.caption))
        self.assertIn(EMPTY, collect(at))


@unittest.skipUnless(APP, "app/ not present in this copy")
class ProjectPages(unittest.TestCase):
    def render(self, page, outputs=None, docs=None):
        src = f"import sys; sys.path.insert(0, r'{APP}')\nfrom views import {page} as v\nv.render()\n"
        with mock.patch.object(data, "OUTPUTS", outputs or data.OUTPUTS), mock.patch.object(data, "DOCS", docs or data.DOCS):
            return AppTest.from_string(src, default_timeout=120).run()

    def test_banner_names_the_source_files_and_their_dates(self):
        for page, key in (("evaluations", "evaluations"), ("architecture", "architecture")):
            at = self.render(page)
            self.assertEqual([e.value for e in at.exception], [], page)
            text = " ".join(m.value for m in at.markdown)
            self.assertIn("Project-level results, not from a run", text)
            for rel, date in data.project_sources(key):
                self.assertIn(rel, text)
                self.assertRegex(date, r"^\d{4}-\d{2}-\d{2}$|^file not found$")
                self.assertIn(date, text)

    def test_project_pages_open_only_their_declared_files(self):
        for page, key in (("evaluations", "evaluations"), ("architecture", "architecture")):
            with OpenSpy() as spy:
                self.render(page)
            self.assertEqual(stray(spy.opened, None, Path(tempfile.gettempdir()), extra=data.project_files(key)), [], page)

    def test_project_pages_do_not_depend_on_a_run(self):
        with tempfile.TemporaryDirectory() as t:
            out, docs = Path(t) / "outputs", Path(t) / "docs"
            out.mkdir()
            docs.mkdir()
            (out / "eval_results.json").write_text(json.dumps(
                {"generated_at": "2026-10-22", "unit": {"passed": 7, "total": 9, "source": "x"}, "golden": {"passed": 3, "total": 3, "cases": []},
                 "mutation": None}), encoding="utf-8")
            at = self.render("evaluations", outputs=out, docs=docs)
        self.assertEqual([e.value for e in at.exception], [])
        self.assertEqual({m.label: m.value for m in at.metric}["Unit tests"], "7/9")
        self.assertNotIn("Showing: Run", " ".join(m.value for m in at.markdown))


if __name__ == "__main__":
    unittest.main()
