# scan-secrets: allow-fake-fixtures  (CANARIES below are invented values, used to prove they are never displayed)
"""The workspace app displays engine output and nothing else.

Runs every page headless (streamlit AppTest) for abc and xyz and checks:
  1. every $ amount, % and pp shown on a page is a formatted value that exists in the engine JSON, and key
     figures equal the engine value exactly;
  2. no page imports a calculation module (static scan + a clean interpreter);
  3. no token, realm ID or .env-style content reaches any rendered output, even if a JSON file contains one;
  4. empty states render, without errors, when outputs are missing;
  5. an approved period renders as locked.

Needs outputs from `python scripts/run_pipeline.py abc 2026-06` and `... xyz 2026-05`; the number and secret
tests skip with a message if they are missing. All tests skip when app/ is absent (e.g. the mutation-test copy).
"""
import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
APP = next((p for p in (ROOT / "app", ROOT.parent / "app") if (p / "Home.py").is_file()), None)
OUTPUTS = ROOT.parent / "outputs"
CLIENTS = {"abc": "2026-06", "xyz": "2026-05"}
PAGES = ["overview", "analysis", "insights", "datasources", "runs", "evaluations", "architecture"]
FORBIDDEN = {"abc_workbook_adapter", "financial_analysis", "monthly_review", "run_client", "close_artifacts",
             "client_sandbox", "openpyxl", "numpy", "scipy"}

if APP:
    sys.path.insert(0, str(APP))
    sys.path.insert(0, str(ROOT / "scripts"))
    from streamlit.testing.v1 import AppTest
    import data
    import ui
    import scan_secrets

TOKEN = {"money": re.compile(r"\$[\d,]+(?:\.\d+)?"), "pct": re.compile(r"\d+(?:\.\d+)?%"),
         "pp": re.compile(r"\d+(?:\.\d+)? pp")}
# Fake credentials that must never be displayed even if they land in a JSON file.
CANARIES = ["eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjYW5hcnkifQ.c2lnbmF0dXJlMTIz", "realmId=9130350000000001",
            "refresh_token: RT1-canary0123456789abcdefghijklmnop", "Bearer canarycanarycanarycanary0123"]


def render(page, outputs=None, docs=None, client="abc", period="2026-06"):
    src = (f"import sys; sys.path.insert(0, r'{APP}')\nimport streamlit as st\nfrom views import {page} as v\n"
           f"st.session_state['ctx'] = {{'client': {client!r}, 'period': {period!r}}}\nv.render()\n")
    with mock.patch.object(data, "OUTPUTS", outputs or OUTPUTS), mock.patch.object(data, "DOCS", docs or data.DOCS):
        return AppTest.from_string(src, default_timeout=120).run()


def collect(at):
    """Every string a user could see: labels, values, deltas, dataframe headers and cells."""
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
            for attr in ("value", "body", "label", "delta", "help", "proto"):
                try:
                    v = getattr(el, attr)
                except Exception:
                    continue
                add(v if attr != "proto" else None)
            if hasattr(el, "children"):
                walk(el)

    walk(at.main)
    return "\n".join(out)


def tokens(text):
    return {kind: set(rx.findall(text)) for kind, rx in TOKEN.items()}


def numbers_in(obj):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from numbers_in(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from numbers_in(v)


def allowed_tokens(client, period):
    """All $ / % / pp strings obtainable by formatting a number that appears in this client's engine JSON."""
    allowed = {k: set() for k in TOKEN}
    files = [p for p in (OUTPUTS / client).glob("*.json") if not p.name.startswith(("manifest", "qbo_"))]
    files += [OUTPUTS / "commentary_grade.json", OUTPUTS / "eval_results.json"]  # global: the Evaluations page
    for p in files:
        raw = p.read_text(encoding="utf-8")
        for k, t in tokens(raw).items():  # amounts the engine already wrote as text (commentary lines, grader tokens)
            allowed[k] |= t
        for v in numbers_in(json.loads(raw)):
            for s in (ui.money(v), ui.money2(v), ui.pct(v), ui.pp(v) or "", f"{v * 100:.2f}%"):  # 2 dp: the commentary text prints percentages that way
                for k, t in tokens(s).items():
                    allowed[k] |= t
    return allowed


def have_outputs(client):
    return (OUTPUTS / client / f"review_packet_{CLIENTS[client]}.json").is_file()


def js(client, name):
    return json.loads((OUTPUTS / client / name).read_text(encoding="utf-8"))


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
                "from views import analysis, architecture, datasources, evaluations, insights, overview, runs\n"
                f"print([m for m in {sorted(FORBIDDEN - {'numpy', 'scipy'})!r} if m in sys.modules])")  # pandas itself loads numpy
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=tempfile.gettempdir())
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertEqual(r.stdout.strip(), "[]")


@unittest.skipUnless(APP, "app/ not present in this copy")
class NumbersMatchEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rendered = {}
        for client, period in CLIENTS.items():
            if have_outputs(client):
                for page in PAGES:
                    cls.rendered[client, page] = render(page, client=client, period=period)

    def need(self, client, page):
        if (client, page) not in self.rendered:
            self.skipTest(f"no outputs for {client}; run scripts/run_pipeline.py {client} {CLIENTS[client]}")
        return self.rendered[client, page]

    def test_pages_render_without_exceptions(self):
        for (client, page), at in self.rendered.items():
            self.assertEqual([e.value for e in at.exception], [], f"{client}/{page}")

    def test_every_displayed_amount_and_percentage_exists_in_engine_json(self):
        for client, period in CLIENTS.items():
            allowed = allowed_tokens(client, period) if have_outputs(client) else None
            for page in PAGES:
                shown = tokens(collect(self.need(client, page)))
                for kind, vals in shown.items():
                    stray = vals - allowed[kind]
                    self.assertFalse(stray, f"{client}/{page}: {kind} not in engine JSON: {sorted(stray)[:5]}")

    def test_overview_key_figures_equal_engine_values(self):
        for client, period in CLIENTS.items():
            at = self.need(client, "overview")
            pk = js(client, f"review_packet_{period}.json")
            m = pk["months"][period]
            metrics = {x.label: x for x in at.metric}
            rev, ni = m["revenue"], m["net_income"]
            self.assertEqual(metrics["Revenue"].value, ui.money(rev["value"]))
            self.assertEqual(metrics["Revenue"].delta, ui.delta(rev.get("mom_change"), rev.get("mom_pct")))
            self.assertEqual(metrics["Gross margin"].value, ui.pct(m["gross_profit"]["margin"]))
            self.assertEqual(metrics["Operating expenses"].value, ui.money(m["operating_expenses"]["value"]))
            self.assertEqual(metrics["Operating income"].value, ui.money(m["operating_income"]["value"]))
            self.assertEqual(metrics["Net income"].value, ui.money(ni["value"]))
            cash = pk.get("cash") or {}
            self.assertEqual(metrics["Cash"].value, ui.money(cash["value"]) if cash else "n/a")
            if cash:
                win = cash["primary_window"]
                self.assertEqual(metrics[f"Runway ({win} burn)"].value, f"{cash['runway_months'][win]:.1f} months")

    def test_revenue_by_stream_table_matches_tables_json(self):
        for client, period in CLIENTS.items():
            at = self.need(client, "analysis")
            tb = js(client, f"tables_{period}.json")
            frames = [d.value for d in at.dataframe]
            streams = next(f for f in frames if set(f["Item"]) == set(tb["revenue_by_stream"]))
            for _, row in streams.iterrows():
                for mo in tb["months"]:
                    self.assertEqual(row[mo], ui.money(tb["revenue_by_stream"][row["Item"]].get(mo)), f"{client} {row['Item']} {mo}")

    def test_ttm_is_not_available_before_twelve_months(self):
        for client, period in CLIENTS.items():
            at = self.need(client, "analysis")
            pk = js(client, f"review_packet_{period}.json")
            ttm = next(d.value for d in at.dataframe if "Month" in d.value.columns and
                       not any("Δ" in c or "margin" in c.lower() for c in d.value.columns))
            for _, row in ttm.iterrows():
                t = pk["months"][row["Month"]]["revenue"]["ttm"]
                self.assertEqual(row["Revenue"], "not available" if t is None else ui.money(t), f"{client} {row['Month']}")
        if have_outputs("abc"):
            ttm = next(d.value for d in self.rendered["abc", "analysis"].dataframe
                       if "Month" in d.value.columns and not any("Δ" in c or "margin" in c.lower() for c in d.value.columns))
            by = dict(zip(ttm["Month"], ttm["Revenue"]))
            self.assertEqual(by["2025-11"], "not available")
            self.assertNotEqual(by["2025-12"], "not available")

    def test_flux_table_is_sorted_by_absolute_dollar_change_with_engine_severity(self):
        for client, period in CLIENTS.items():
            at = self.need(client, "insights")
            flux = js(client, f"flux_{period}.json")["items"]
            if not flux:
                continue
            table = next(d.value for d in at.dataframe if "Severity" in d.value.columns)
            want = sorted(flux, key=lambda i: abs(i["dollar_change"]), reverse=True)
            self.assertEqual(list(table["Account"]), [i["account"] for i in want])
            self.assertEqual(list(table["$ change"]), [ui.money2(i["dollar_change"]) for i in want])
            self.assertEqual(list(table["Severity"]), [i["severity"].title() for i in want])

    def test_reviewer_explanations_are_not_shown(self):
        path = OUTPUTS / "abc" / "review_2026-06.json"
        if not path.is_file():
            self.skipTest("no reviewer output for abc")
        text = collect(self.need("abc", "insights"))
        for q in json.loads(path.read_text(encoding="utf-8"))["open_questions"]:
            self.assertIn(q["question"], text)
            self.assertNotIn(q["why"], text)

    def test_no_secrets_in_any_rendered_page(self):
        for (client, page), at in self.rendered.items():
            text = collect(at)
            hits = [(n, k) for n, k in scan_secrets.scan_text(text) if k not in scan_secrets.INFO_ONLY]
            self.assertEqual(hits, [], f"{client}/{page}")
            self.assertIsNone(re.search(r"(?m)^[A-Z][A-Z0-9_]{3,}=\S", text), f"{client}/{page}: env-style line")


@unittest.skipUnless(APP, "app/ not present in this copy")
class WithTemporaryOutputs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "outputs"
        self.out.mkdir()
        self.addCleanup(self.tmp.cleanup)

    def test_empty_states_render_when_there_are_no_clients(self):
        for page in PAGES:
            at = render(page, outputs=self.out, docs=self.out)
            self.assertEqual([e.value for e in at.exception], [], page)
            if page != "architecture":
                self.assertIn("No data", collect(at), page)

    def test_empty_states_render_when_a_client_has_no_engine_files(self):
        (self.out / "abc").mkdir()
        (self.out / "abc" / "summary.json").write_text("{}", encoding="utf-8")
        for page in PAGES:
            at = render(page, outputs=self.out, docs=self.out, period=None)
            self.assertEqual([e.value for e in at.exception], [], page)
            if page != "architecture":
                self.assertIn("No data", collect(at), page)
        self.assertIn("No data", collect(render("architecture", outputs=self.out, docs=self.out)))

    def test_unreadable_json_shows_an_empty_state_not_a_traceback(self):
        d = self.out / "abc"
        d.mkdir()
        (d / "summary.json").write_text("{}", encoding="utf-8")
        (d / "review_packet_2026-06.json").write_text("{not json", encoding="utf-8")
        at = render("overview", outputs=self.out)
        self.assertEqual([e.value for e in at.exception], [])
        self.assertIn("No data", collect(at))

    def test_credentials_in_a_json_file_are_withheld(self):
        if not have_outputs("abc"):
            self.skipTest("no outputs for abc")
        d = self.out / "abc"
        shutil.copytree(OUTPUTS / "abc", d)
        status = {"method": "x", "flags": {}, "last_successful_retrieval": "2026-10-12",
                  "last_test": {"tested_at": "t", "ok": False, "message": " | ".join(CANARIES)}}
        (d / "qbo_status.json").write_text(json.dumps(status), encoding="utf-8")
        text = collect(render("datasources", outputs=self.out))
        for c in CANARIES:
            self.assertNotIn(c, text)
            self.assertNotIn(c.split(":")[-1].split("=")[-1].strip(), text)
        self.assertIn("[withheld]", text)

    def test_approved_period_renders_as_locked(self):
        if not have_outputs("abc"):
            self.skipTest("no outputs for abc")
        d = self.out / "abc"
        shutil.copytree(OUTPUTS / "abc", d)
        (d / "approval_2026-06.json").write_text(json.dumps(
            {"status": "approved", "reviewer": "T. Reviewer", "reason": "ok", "decided_at": "2026-10-14T00:00:00+00:00"}),
            encoding="utf-8")
        at = render("insights", outputs=self.out)
        self.assertEqual([e.value for e in at.exception], [])
        self.assertIn("Locked - approved", collect(at))
        self.assertEqual(len(at.text_input), 0, "decision form must not render for a locked period")
        self.assertIn("Locked - approved", collect(render("overview", outputs=self.out)))


if __name__ == "__main__":
    unittest.main()
