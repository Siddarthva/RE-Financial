"""qbo_adapter: QuickBooks report JSON -> the engine's frames. Mapping, missing month (WARN), unmapped account (WARN),
report-shape change (STOP), and the saved sandbox capture end to end through the intake checks."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import abc_workbook_adapter as engine  # noqa: E402
import qbo_adapter  # noqa: E402
import run_client  # noqa: E402
import sources  # noqa: E402

SECTIONS = {"income": ("Income", "Total Income"), "cost of goods sold": ("Cost of Goods Sold", "Total Cost of Goods Sold"),
            "operating expenses": ("Expenses", "Total Expenses")}


def _col(month):
    p = pd.Period(month, "M")
    return {"ColTitle": p.strftime("%b %Y"), "ColType": "Money", "MetaData": [
        {"Name": "StartDate", "Value": f"{p.start_time:%Y-%m-%d}"}, {"Name": "EndDate", "Value": f"{p.end_time:%Y-%m-%d}"}]}


def _cd(label, vals, id_=None):
    first = {"value": label, **({"id": id_} if id_ else {})}
    return [first] + [{"value": "" if v is None else f"{v:.2f}"} for v in vals] + [{"value": f"{sum(v or 0 for v in vals):.2f}"}]


def report(months=("2026-01", "2026-02", "2026-03"), extra_expense=None, extra_group=None):
    """A small ProfitAndLoss in QuickBooks' shape: sections, a parent account with its own posting and a child."""
    n = len(months)
    sales, mats = [100.0 + 10 * i for i in range(n)], [40.0 + 4 * i for i in range(n)]
    rent, util_own, phone = [10.0] * n, [1.0] * n, [None] + [5.0] * (n - 1)  # '' in QuickBooks = no activity = 0
    exp_rows = [{"ColData": _cd("Rent", rent), "type": "Data"},
                {"Header": {"ColData": _cd("Utilities", util_own, "24")}, "Rows": {"Row": [{"ColData": _cd("Telephone", phone, "77")}]},
                 "Summary": {"ColData": _cd("Total Utilities", [u + (p or 0) for u, p in zip(util_own, phone)])}}]
    extra = [0.0] * n
    if extra_expense:
        extra = [3.0] * n
        exp_rows.append({"ColData": _cd(extra_expense, extra)})
    opex = [r + u + (p or 0) + e for r, u, p, e in zip(rent, util_own, phone, extra)]
    gp = [s - m for s, m in zip(sales, mats)]
    rows = [
        {"Header": {"ColData": _cd("Income", [None] * n)}, "Rows": {"Row": [{"ColData": _cd("Sales", sales, "1")}]},
         "Summary": {"ColData": _cd("Total Income", sales)}, "group": "Income"},
        {"Header": {"ColData": _cd("Cost of Goods Sold", [None] * n)}, "Rows": {"Row": [{"ColData": _cd("Materials", mats, "80")}]},
         "Summary": {"ColData": _cd("Total Cost of Goods Sold", mats)}, "group": "COGS"},
        {"Summary": {"ColData": _cd("Gross Profit", gp)}, "group": "GrossProfit"},
        {"Header": {"ColData": _cd("Expenses", [None] * n)}, "Rows": {"Row": exp_rows},
         "Summary": {"ColData": _cd("Total Expenses", opex)}, "group": "Expenses"},
        {"Summary": {"ColData": _cd("Net Operating Income", [g - o for g, o in zip(gp, opex)])}, "group": "NetOperatingIncome"},
    ]
    if extra_group:
        rows.append({"Header": {"ColData": _cd(extra_group, [None] * n)}, "Rows": {"Row": [{"ColData": _cd("Odd", [1.0] * n)}]},
                     "Summary": {"ColData": _cd(f"Total {extra_group}", [1.0] * n)}})
    rows.append({"Summary": {"ColData": _cd("Net Income", [g - o for g, o in zip(gp, opex)])}, "group": "NetIncome"})
    return {"Header": {"ReportName": "ProfitAndLoss", "SummarizeColumnsBy": "Month"},
            "Columns": {"Column": [{"ColTitle": "", "ColType": "Account"}] + [_col(m) for m in months]
                        + [{"ColTitle": "Total", "ColType": "Money"}]},
            "Rows": {"Row": rows}}


def parse(rep, **kw):
    return qbo_adapter.parse_report(rep, "ProfitAndLoss", SECTIONS, **kw)


def cfg_for(am, mapping):
    return {"account_to_category": mapping, "categories": sorted(set(mapping.values()))}


class MappingTests(unittest.TestCase):
    def test_sections_totals_and_qualified_names(self):
        am = parse(report())
        jan = pd.Timestamp("2026-01-01")
        self.assertEqual(am.attrs["sections"]["Sales"], "income")
        self.assertEqual(am.attrs["sections"]["Utilities:Telephone"], "operating expenses")
        self.assertIsNone(am.attrs["sections"]["Total Income"])  # a section total closes its section, as in the workbook parser
        self.assertEqual(am.at["Utilities", jan], 1.0)  # parent's own posting, from the Header row
        self.assertEqual(am.at["Utilities:Telephone", jan], 0.0)  # empty QuickBooks cell = no activity
        self.assertNotIn("Total Utilities", am.index)  # parent subtotal is checked, not emitted (no double count)
        monthly = engine.build_monthly_summary(am, {"revenue": "Total Income", "cost_of_goods_sold": "Total Cost of Goods Sold",
                                                   "gross_profit": "Gross Profit", "operating_expenses": "Total Expenses",
                                                   "operating_income": "Net Operating Income", "net_income": "Net Income"})
        self.assertAlmostEqual(monthly["gross_margin_pct"].iloc[-1], (120 - 48) / 120)

    def test_category_mapping_by_account_name(self):
        am = parse(report())
        trends = engine.build_expense_category_trends(am, [])
        rollup = engine.build_category_rollup(trends, {"Rent": "Occupancy", "Utilities": "Occupancy", "Utilities:Telephone": "Tech"})
        feb = rollup[rollup["month"] == pd.Timestamp("2026-02-01")].set_index("category")["amount"]
        self.assertEqual(feb.to_dict(), {"Occupancy": 11.0, "Tech": 5.0})

    def test_cell_refs_name_report_row_and_month(self):
        am = parse(report())
        self.assertEqual(engine.cell_name(am, "Rent", pd.Timestamp("2026-03-01")), "ProfitAndLoss!Rent[Mar 2026]")


class WarnTests(unittest.TestCase):
    def test_unmapped_account_warns(self):
        am = parse(report(extra_expense="Mystery Fees"))
        trends = engine.build_expense_category_trends(am, [])
        mapping = {"Rent": "Occupancy", "Utilities": "Occupancy", "Utilities:Telephone": "Occupancy"}
        rollup = engine.build_category_rollup(trends, mapping)
        monthly = engine.build_monthly_summary(am, {"revenue": "Total Income", "operating_expenses": "Total Expenses",
                                                   "gross_profit": "Gross Profit", "net_income": "Net Income"})
        warnings = run_client.data_quality(cfg_for(am, mapping), am, monthly, trends, rollup)
        self.assertIn("Unmapped OPEX account (reported under 'Unmapped'): Mystery Fees", warnings)

    def test_missing_month_warns(self):
        am = parse(report(months=("2026-01", "2026-02", "2026-04", "2026-05")))
        self.assertEqual([f"{m:%Y-%m}" for m in am.columns], ["2026-01", "2026-02", "2026-04", "2026-05"])
        trends = engine.build_expense_category_trends(am, [])
        mapping = {"Rent": "Occupancy", "Utilities": "Occupancy", "Utilities:Telephone": "Occupancy"}
        rollup = engine.build_category_rollup(trends, mapping)
        monthly = engine.build_monthly_summary(am, {"revenue": "Total Income", "operating_expenses": "Total Expenses",
                                                   "gross_profit": "Gross Profit", "net_income": "Net Income"})
        warnings = run_client.data_quality(cfg_for(am, mapping), am, monthly, trends, rollup)
        self.assertTrue(any(w.startswith("Months missing from the source: Mar 2026") for w in warnings), warnings)

    def test_unknown_top_level_group_warns_not_stops(self):
        am = parse(report(extra_group="Other Income"))
        self.assertTrue(any("'Other Income' is not mapped" in n for n in am.attrs["source_notes"]))
        am = parse(report(extra_group="Other Income"), other_groups=["Other Income"])
        self.assertEqual(am.attrs["source_notes"], [])


class StopTests(unittest.TestCase):
    def assertStops(self, rep, text):
        with self.assertRaises(qbo_adapter.ShapeError) as cm:
            parse(rep)
        self.assertIn(text, str(cm.exception))

    def test_other_report(self):
        rep = report()
        rep["Header"]["ReportName"] = "BalanceSheet"
        self.assertStops(rep, "expected a ProfitAndLoss report")

    def test_not_monthly(self):
        rep = report()
        rep["Header"]["SummarizeColumnsBy"] = "Total"
        self.assertStops(rep, "not 'Month'")

    def test_missing_rows_key(self):
        rep = report()
        del rep["Rows"]
        self.assertStops(rep, "report shape changed")

    def test_row_with_wrong_number_of_cells(self):
        rep = report()
        rep["Rows"]["Row"][0]["Rows"]["Row"][0]["ColData"].pop()
        self.assertStops(rep, "row 'Sales' has 4 cells, expected 5")

    def test_partial_month_column(self):
        rep = report()
        rep["Columns"]["Column"][2]["MetaData"][1]["Value"] = "2026-02-14"
        self.assertStops(rep, "not one whole calendar month")

    def test_duplicate_account_name(self):
        rep = report()
        rows = rep["Rows"]["Row"][3]["Rows"]["Row"]
        rows.append(copy.deepcopy(rows[0]))
        self.assertStops(rep, "account name 'Rent' appears twice")

    def test_subtotal_that_does_not_foot(self):
        rep = report()
        rep["Rows"]["Row"][3]["Rows"]["Row"][1]["Summary"]["ColData"][2]["value"] = "999.00"
        self.assertStops(rep, "'Total Utilities' in Feb 2026")

    def test_intake_refuses_a_tampered_capture_with_named_cause(self):
        cfg = run_client.load_config("qbo_sandbox")
        rep = json.loads(Path(cfg["workbook_path"]).read_text(encoding="utf-8"))
        rep["Header"]["SummarizeColumnsBy"] = "Quarter"
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "pnl.json"
            bad.write_text(json.dumps(rep), encoding="utf-8")
            problems = sources.frame_preflight({**cfg, "workbook_path": bad}, "2026-09")
        self.assertEqual(len(problems), 1)
        self.assertIn("summarized by 'Quarter'", problems[0])


class SavedSandboxCaptureTests(unittest.TestCase):
    """The redacted 2026-10-22 capture (Intuit sample company), through the same path as the pipeline."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = run_client.load_config("qbo_sandbox")
        cls.am, cls.bs = qbo_adapter.load(cls.cfg)

    def test_leading_empty_months_are_left_out_and_named(self):
        self.assertEqual(f"{self.am.columns[0]:%Y-%m}", "2026-05")
        self.assertEqual(list(self.am.columns), list(self.bs.columns))
        self.assertTrue(any("18 month(s) before May 2026" in n for n in self.am.attrs["source_notes"]))

    def test_same_leaf_name_in_two_sections_stays_two_accounts(self):
        s = self.am.attrs["sections"]
        self.assertEqual(s["Landscaping Services:Job Materials:Plants and Soil"], "income")
        self.assertEqual(s["Job Expenses:Job Materials:Plants and Soil"], "operating expenses")

    def test_every_opex_account_is_mapped(self):
        opex = {a for a, sec in self.am.attrs["sections"].items() if sec == "operating expenses"}
        self.assertEqual(opex - set(self.cfg["account_to_category"]), set())

    def test_intake_passes(self):
        self.assertEqual(sources.frame_preflight(self.cfg, "2026-09"), [])


if __name__ == "__main__":
    unittest.main()
