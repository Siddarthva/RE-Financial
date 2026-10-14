import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from client_sandbox import client_sandbox
from run_client import CLIENTS_ROOT, run


def norm(p):
    return os.path.normcase(os.path.realpath(p))


class ClientIsolationTests(unittest.TestCase):
    """A run for one client cannot read or write the other client's folder or outputs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.outputs = Path(self.tmp.name) / "outputs"
        (self.outputs / "xyz").mkdir(parents=True)
        (self.outputs / "xyz" / "private.txt").write_text("xyz only", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_abc_run_touches_nothing_belonging_to_xyz(self):
        from run_client import run as run_client
        import client_sandbox as sb
        seen = []
        original = sb.ClientSandbox.check
        def spy(self_, path, write):
            seen.append((write, norm(path)))
            return original(self_, path, write)
        sb.ClientSandbox.check = spy
        try:
            run_client("abc", CLIENTS_ROOT, self.outputs)
        finally:
            sb.ClientSandbox.check = original
        forbidden = [norm(CLIENTS_ROOT / "xyz"), norm(self.outputs / "xyz")]
        self.assertTrue(seen, "sandbox saw no file access; the audit hook is not active")
        self.assertFalse([p for _, p in seen if any(p.startswith(f) for f in forbidden)])
        writes = [p for w, p in seen if w]
        self.assertTrue(writes and all(p.startswith(norm(self.outputs / "abc")) for p in writes), writes)

    def test_each_run_writes_only_its_own_output_folder(self):
        run("abc", CLIENTS_ROOT, self.outputs)
        run("xyz", CLIENTS_ROOT, self.outputs)
        files = sorted(str(p.relative_to(self.outputs)).replace(os.sep, "/") for p in self.outputs.rglob("*") if p.is_file())
        self.assertEqual(files, ["abc/analysis.xlsx", "abc/commentary.md", "abc/summary.json",
                                 "xyz/analysis.xlsx", "xyz/commentary.md", "xyz/private.txt", "xyz/summary.json"])
        self.assertEqual((self.outputs / "xyz" / "private.txt").read_text(encoding="utf-8"), "xyz only")

    def test_reading_other_client_folder_or_outputs_is_blocked(self):
        with client_sandbox("abc", CLIENTS_ROOT, self.outputs):
            with self.assertRaises(PermissionError):
                (CLIENTS_ROOT / "xyz" / "config.yaml").read_text(encoding="utf-8")
            with self.assertRaises(PermissionError):
                pd.read_excel(CLIENTS_ROOT / "xyz" / "xyz_financials.xlsx")
            with self.assertRaises(PermissionError):
                (self.outputs / "xyz" / "private.txt").read_text(encoding="utf-8")
            (CLIENTS_ROOT / "abc" / "config.yaml").read_text(encoding="utf-8")  # own folder still readable

    def test_writing_outside_own_output_folder_is_blocked(self):
        with client_sandbox("xyz", CLIENTS_ROOT, self.outputs):
            with self.assertRaises(PermissionError):
                (self.outputs / "abc").mkdir()
            with self.assertRaises(PermissionError):
                open(self.outputs / "abc_leak.txt", "w").close()
            with self.assertRaises(PermissionError):
                os.remove(self.outputs / "xyz" / ".." / "xyz" / ".." / "abc_leak.txt")
            with self.assertRaises(PermissionError):
                open(CLIENTS_ROOT / "xyz" / "config.yaml", "a").close()  # own *input* folder is read-only too
            (self.outputs / "xyz" / "ok.txt").write_text("fine", encoding="utf-8")
        self.assertFalse((self.outputs / "abc").exists())

    def test_config_pointing_at_other_client_data_is_rejected(self):
        clients = Path(self.tmp.name) / "clients"
        shutil.copytree(CLIENTS_ROOT / "xyz", clients / "xyz")
        (clients / "abc").mkdir()
        cfg = (CLIENTS_ROOT / "abc" / "config.yaml").read_text(encoding="utf-8")
        cfg = cfg.replace("workbook: ../../data/ABC Inc - Financial Statements.xlsx", "workbook: ../xyz/xyz_financials.xlsx")
        (clients / "abc" / "config.yaml").write_text(cfg, encoding="utf-8")
        with self.assertRaises(PermissionError):
            run("abc", clients, self.outputs)
        self.assertFalse((self.outputs / "abc" / "analysis.xlsx").exists())

    def test_short_and_long_path_spellings_cannot_bypass_the_guard(self):
        # Regression: Windows 8.3 names (e.g. SIDDAR~1) once let a long-form path skip the prefix check.
        clients = Path(self.tmp.name) / "clients"
        shutil.copytree(CLIENTS_ROOT / "xyz", clients / "xyz")
        (clients / "abc").mkdir()
        long_form = Path(os.path.realpath(clients)) / "xyz" / "config.yaml"
        with client_sandbox("abc", clients, self.outputs):
            with self.assertRaises(PermissionError):
                long_form.read_text(encoding="utf-8")

    def test_run_works_when_outputs_folder_does_not_exist_yet(self):
        # A fresh checkout has no outputs/; the sandbox must create it before it starts blocking writes.
        fresh = Path(self.tmp.name) / "fresh" / "outputs"
        paths = run("abc", CLIENTS_ROOT, fresh)
        self.assertTrue(paths["summary"].exists())
        self.assertTrue(str(paths["summary"].resolve()).startswith(str((fresh / "abc").resolve())))

    def test_sandbox_is_off_outside_a_run(self):
        run("abc", CLIENTS_ROOT, self.outputs)
        (self.outputs / "after.txt").write_text("unrestricted again", encoding="utf-8")


class ClientConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        out = Path(cls.tmp.name)
        cls.abc = json.loads(run("abc", CLIENTS_ROOT, out)["summary"].read_text(encoding="utf-8"))
        cls.xyz = json.loads(run("xyz", CLIENTS_ROOT, out)["summary"].read_text(encoding="utf-8"))
        cls.xyz_book = pd.read_excel(out / "xyz" / "analysis.xlsx", sheet_name=None)
        cls.abc_book = pd.read_excel(out / "abc" / "analysis.xlsx", sheet_name=None)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_abc_config_reproduces_existing_engine_numbers(self):
        self.assertEqual(self.abc["period"], "Jan 2025 - Jun 2026")
        self.assertAlmostEqual(self.abc["latest"]["revenue"], 195898.16, places=2)     # C14
        self.assertAlmostEqual(self.abc["latest"]["net_income"], -330756.08, places=2)  # C107
        self.assertAlmostEqual(self.abc["latest"]["revenue_ttm"], 2303975.51, places=2)  # SUM(C14:N14)
        self.assertEqual(self.abc["warnings"], [])

    def test_abc_fiscal_ytd_matches_balance_sheet_current_year_earnings(self):
        self.assertEqual(self.abc["latest_fiscal_year"], "FY2026")
        self.assertAlmostEqual(self.abc["latest"]["net_income_fytd"], -1987916.44, places=2)  # Balance Sheet D63

    def test_category_rollups_sum_to_total_opex_every_month(self):
        for book in (self.abc_book, self.xyz_book):
            sums = book["Expense Categories"].groupby("month")["amount"].sum()
            totals = book["Monthly Trends"].set_index("month")["operating_expenses"]
            for m, total in totals.items():
                self.assertAlmostEqual(sums[m], total, places=2, msg=str(m))

    def test_xyz_missing_category_reported_not_zero_filled(self):
        self.assertIn("Missing category: no 'Sales & Marketing' accounts in the source; reported as not available, not zero.",
                      self.xyz["warnings"])
        self.assertNotIn("Sales & Marketing", set(self.xyz_book["Expense Categories"]["category"]))
        self.assertNotIn("Sales & Marketing", self.xyz["categories_latest"])

    def test_xyz_layout_fiscal_year_and_ttm(self):
        monthly = self.xyz_book["Monthly Trends"]
        self.assertEqual(self.xyz["period"], "Apr 2025 - May 2026")
        self.assertEqual(monthly["fiscal_year"].tolist(), ["FY2025-26"] * 12 + ["FY2026-27"] * 2)
        self.assertEqual(int(monthly["revenue_ttm"].first_valid_index()), 11)  # Mar 2026 = 12th month
        apr26 = monthly.iloc[12]
        self.assertAlmostEqual(apr26["revenue_fytd"], apr26["revenue"], places=2)  # FYTD restarts in April
        # Net Profit = Operating Profit - Finance Costs, so it differs from operating income.
        self.assertTrue((monthly["net_income"] < monthly["operating_income"]).all())

    def test_xyz_one_off_audit_fee_detected(self):
        one_offs = self.xyz_book["One-off Items"]
        self.assertEqual(one_offs["account"].tolist(), ["Audit Fees"])
        self.assertEqual(pd.Timestamp(one_offs["month"].iloc[0]), pd.Timestamp("2025-09-01"))


if __name__ == "__main__":
    unittest.main()
