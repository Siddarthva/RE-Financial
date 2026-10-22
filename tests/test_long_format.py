"""Long-format layout (layout.type: long): same internal structure as the wide parser, proved on the ABC workbook converted
in memory to long format (temp file; data/ is only read), plus the long-format STOP/WARN rules."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd
import yaml
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import abc_workbook_adapter as engine  # noqa: E402
import monthly_review  # noqa: E402
import run_client  # noqa: E402
import sources  # noqa: E402

WORKBOOK = ROOT / "data" / "ABC Inc - Financial Statements.xlsx"
LONG_LAYOUT = {"type": "long", "month_format": "%Y-%m",
               "columns": {"account": "Account", "month": "Month", "amount": "Amount", "section": "Section"}}


def abc_long_client(root: Path) -> Path:
    """clients/abc copied to `root` with the workbook converted to long format and layout.type: long."""
    am = engine.parse_wide_income_statement(WORKBOOK)
    bs = engine.parse_wide_income_statement(WORKBOOK, engine.ABC_BS_LAYOUT)
    cdir = root / "abc"
    cdir.mkdir(parents=True)
    engine.write_long_workbook({"Income Statement": am, "Balance Sheet": bs}, cdir / "abc_long.xlsx")
    cfg = yaml.safe_load((ROOT / "clients" / "abc" / "config.yaml").read_text(encoding="utf-8"))
    cfg.update(workbook="abc_long.xlsx", layout=LONG_LAYOUT)
    (cdir / "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return root


class AbcLongEquivalenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        clients = abc_long_client(t / "clients")
        monthly_review.prepare("abc", "2026-06", clients, t / "out_long")
        monthly_review.prepare("abc", "2026-06", run_client.CLIENTS_ROOT, t / "out_wide")
        read = lambda d: json.loads((t / d / "abc" / "review_packet_2026-06.json").read_text(encoding="utf-8"))
        cls.long, cls.wide = read("out_long"), read("out_wide")
        cls.long_intake = json.loads((t / "out_long" / "abc" / "intake_2026-06.json").read_text(encoding="utf-8"))
        cls.workbook_sha_before = engine  # placeholder so the attribute exists if setUp fails early

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_packet_numbers_identical_to_wide_run(self):
        strip = lambda p: {k: v for k, v in p.items() if k != "warnings"}
        self.assertEqual(strip(self.long), strip(self.wide))

    def test_same_warnings_apart_from_cell_positions(self):
        self.assertEqual(len(self.long["warnings"]), len(self.wide["warnings"]))
        norm = lambda w: w.split(" Check ")[0]  # outlier warnings end with the cell to check, which differs by layout
        self.assertEqual([norm(w) for w in self.long["warnings"]], [norm(w) for w in self.wide["warnings"]])

    def test_long_run_passes_the_same_intake_checks(self):
        self.assertEqual(self.long_intake["status"], "pass")
        names = {c["check"] for c in self.long_intake["checks"]}
        for must in ("Gross profit = revenue - COGS (every month)", "Total Operating Expenses foots to its lines (every month)",
                     "Balance Sheet balances (assets = liabilities + equity, every month)",
                     "Current Year Earnings = year-to-date net income (every month)"):
            self.assertIn(must, names)


def long_book(path: Path, rows, header=("Account", "Month", "Amount", "Section")):
    wb = Workbook()
    ws = wb.active
    ws.title = "P&L"
    ws.append(list(header))
    for r in rows:
        ws.append(list(r))
    wb.save(path)
    return path


LAYOUT = {"sheet": "P&L", "month_format": "%Y-%m", "columns": LONG_LAYOUT["columns"],
          "sections": {"income": ("Revenue", "Total Revenue"), "cost of goods sold": ("COGS", "Total COGS"),
                       "operating expenses": ("Opex", "Total Opex")}}
BASE = [("Sales", "2026-01", 100, "Revenue"), ("Sales", "2026-02", 110, "Revenue"),
        ("Rent", "2026-01", 10, "Opex"), ("Rent", "2026-02", 10, "Opex"),
        ("Fees", "2026-01", 0, "Opex"), ("Fees", "2026-02", 5, "Opex")]


class LongParserRuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "long.xlsx"

    def tearDown(self):
        self.tmp.cleanup()

    def parse(self, rows, header=("Account", "Month", "Amount", "Section")):
        return engine.parse_long_income_statement(long_book(self.path, rows, header), LAYOUT)

    def test_same_structure_as_wide(self):
        am = self.parse(BASE)
        self.assertEqual(list(am.index), ["Sales", "Rent", "Fees"])
        self.assertEqual([f"{m:%Y-%m}" for m in am.columns], ["2026-01", "2026-02"])
        self.assertEqual(am.attrs["sections"], {"Sales": "income", "Rent": "operating expenses", "Fees": "operating expenses"})
        self.assertEqual(engine.cell_name(am, "Rent", pd.Timestamp("2026-02-01")), "P&L!C5")

    def test_duplicate_account_month_stops(self):
        with self.assertRaisesRegex(ValueError, r"'Rent' Feb 2026 appears twice, in rows 5 and 8"):
            self.parse(BASE + [("Rent", "2026-02", 10, "Opex")])

    def test_month_missing_for_one_account_warns(self):
        am = self.parse([r for r in BASE if r[:2] != ("Fees", "2026-01")])
        self.assertTrue(pd.isna(am.at["Fees", pd.Timestamp("2026-01-01")]))  # missing, not zero
        self.assertEqual(am.attrs["blank_cells"], [("P&L (no row)", "Fees", "Jan 2026")])
        self.assertTrue(any("1 blank cell(s)" in w for w in run_client.cell_warnings(am)))

    def test_unknown_column_stops_naming_it(self):
        with self.assertRaisesRegex(ValueError, r"unknown column 'Memo' at E1"):
            self.parse([r + ("x",) for r in BASE], header=("Account", "Month", "Amount", "Section", "Memo"))

    def test_missing_configured_column_stops_naming_it(self):
        with self.assertRaisesRegex(ValueError, r"column 'Amount' \(amount\) not found"):
            self.parse(BASE, header=("Account", "Month", "Amt", "Section"))

    def test_unknown_section_and_bad_month_stop(self):
        with self.assertRaisesRegex(ValueError, r"P&L!D2: unknown section 'Income'"):
            self.parse([("Sales", "2026-01", 100, "Income")] + BASE[1:])
        with self.assertRaisesRegex(ValueError, r"P&L!B2: month 'Jan-26' does not match format"):
            self.parse([("Sales", "Jan-26", 100, "Revenue")] + BASE[1:])

    def test_account_in_two_sections_stops(self):
        with self.assertRaisesRegex(ValueError, r"'Rent' is in section 'operating expenses' at row 4 but 'income'"):
            self.parse(BASE[:3] + [("Rent", "2026-02", 10, "Revenue")] + BASE[4:])


class LongConfigTests(unittest.TestCase):
    def test_long_layout_needs_column_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / "clients" / "xyz", root / "xyz")
            cfg = yaml.safe_load((root / "xyz" / "config.yaml").read_text(encoding="utf-8"))
            cfg["layout"] = {"type": "long", "month_format": "%Y-%m"}
            (root / "xyz" / "config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "layout.columns"):
                run_client.load_config("xyz", root)
            cfg["layout"] = {"type": "tall", "month_format": "%Y-%m"}
            (root / "xyz" / "config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "layout.type must be one of"):
                run_client.load_config("xyz", root)

    def test_default_is_wide(self):
        self.assertEqual(sources.kind(run_client.load_config("abc")), "wide")


if __name__ == "__main__":
    unittest.main()
