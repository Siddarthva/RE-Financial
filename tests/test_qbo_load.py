"""01_connection/load_workbook_to_sandbox.py against an in-memory fake QBO. No network, no credentials."""
import importlib.util
import json
import re
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("loader", ROOT / "01_connection" / "load_workbook_to_sandbox.py")
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)

REVENUE, COGS, OPEX = (loader.ACCOUNTS[k][0] for k in ("revenue", "cost_of_goods_sold", "operating_expenses"))


class FakeQbo:
    """Just enough of the QBO API: accounts and journal entries by DocNumber."""

    def __init__(self):
        self.accounts, self.entries, self.posts = {}, {}, []

    def query(self, sql):
        name = re.search(r"= '(.*)'", sql).group(1)
        if "from Account" in sql:
            return {"Account": [self.accounts[name]]} if name in self.accounts else {}
        return {"JournalEntry": [self.entries[name]]} if name in self.entries else {}

    def request(self, method, path, body=None, query=None):
        self.posts.append(path)
        if path == "account":
            acct = {"Id": str(len(self.accounts) + 1), "Name": body["Name"]}
            self.accounts[body["Name"]] = acct
            return {"Account": acct}
        entry = {**body, "Id": str(len(self.entries) + 100)}
        self.entries[body["DocNumber"]] = entry
        return {"JournalEntry": entry}


def signed(entry, account):
    """Debit-positive amount posted to an account."""
    return sum((l["amount"] if l["posting"] == "Debit" else -l["amount"]) for l in entry["lines"] if l["account"] == account)


class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monthly = loader.load_monthly_totals()
        cls.plan = loader.build_plan(cls.monthly)

    def test_every_entry_balances_and_its_p_and_l_effect_is_workbook_net_income(self):
        self.assertEqual(len(self.plan), 18)
        for e in self.plan:
            self.assertEqual(sum(signed(e, a) for a in {l["account"] for l in e["lines"]}), 0, e["doc_number"])
            net_income = -(signed(e, REVENUE) + signed(e, COGS) + signed(e, OPEX))
            self.assertEqual(net_income, e["net_income_workbook"], e["doc_number"])

    def test_dec_2025_negative_opex_posts_as_a_credit(self):
        dec = next(e for e in self.plan if e["doc_number"] == "ABC-2025-12")
        opex = next(l for l in dec["lines"] if l["account"] == OPEX)
        self.assertEqual((opex["posting"], opex["amount"]), ("Credit", Decimal("402142.09")))   # Income Statement I103
        self.assertEqual(dec["net_income_workbook"], Decimal("534551.41"))                     # I107

    def test_jun_2026_amounts_come_from_source_cells(self):
        jun = next(e for e in self.plan if e["doc_number"] == "ABC-2026-06")
        self.assertEqual(-signed(jun, REVENUE), Decimal("195898.16"))   # C14
        self.assertEqual(signed(jun, COGS), Decimal("58472.44"))        # C24
        self.assertEqual(signed(jun, OPEX), Decimal("468181.80"))       # C103
        self.assertEqual(jun["txn_date"], "2026-06-30")


class LoadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = loader.build_plan(loader.load_monthly_totals())

    def test_dry_run_creates_nothing(self):
        api = FakeQbo()
        ids = loader.ensure_accounts(api, apply=False)
        results = loader.run_plan(self.plan, api, ids, apply=False)
        self.assertEqual(api.posts, [])
        self.assertEqual({r["action"] for r in results}, {"would create"})

    def test_apply_is_idempotent(self):
        api = FakeQbo()
        first = loader.run_plan(self.plan, api, loader.ensure_accounts(api, apply=True), apply=True)
        posts_after_first = len(api.posts)
        second = loader.run_plan(self.plan, api, loader.ensure_accounts(api, apply=True), apply=True)
        self.assertEqual({r["action"] for r in first}, {"created"})
        self.assertEqual({r["action"] for r in second}, {"skip"})
        self.assertEqual(len(api.posts), posts_after_first)   # nothing new posted on the re-run
        self.assertEqual((len(api.entries), len(api.accounts)), (18, 4))

    def test_existing_entry_with_different_amounts_is_a_conflict_and_left_alone(self):
        api = FakeQbo()
        ids = loader.ensure_accounts(api, apply=True)
        loader.run_plan(self.plan, api, ids, apply=True)
        api.entries["ABC-2026-06"]["Line"][0]["Amount"] = 1.0
        before = json.dumps(api.entries["ABC-2026-06"], sort_keys=True)
        result = next(r for r in loader.run_plan(self.plan, api, ids, apply=True) if r["doc"] == "ABC-2026-06")
        self.assertEqual(result["action"], "CONFLICT")
        self.assertEqual(json.dumps(api.entries["ABC-2026-06"], sort_keys=True), before)

    def test_apply_without_env_file_stops_before_any_network_call(self):
        missing = Path(tempfile.gettempdir()) / "no_such_qbo_write.env"
        with mock.patch("urllib.request.urlopen") as net, self.assertRaises(SystemExit):
            loader.main(["--apply", "--env-file", str(missing)])
        net.assert_not_called()


class CredentialTests(unittest.TestCase):
    GOOD = {"QBO_WRITE_CLIENT_ID": "a", "QBO_WRITE_CLIENT_SECRET": "b", "QBO_WRITE_REFRESH_TOKEN": "c",
            "QBO_WRITE_REALM_ID": "d", "QBO_WRITE_ENVIRONMENT": "sandbox"}

    def test_accepts_a_complete_sandbox_file(self):
        loader.validate_env(Path("C:/somewhere/qbo_write.env"), dict(self.GOOD))

    def test_refuses_production_missing_keys_and_the_mcp_env(self):
        bad = [(Path("x/qbo_write.env"), {**self.GOOD, "QBO_WRITE_ENVIRONMENT": "production"}),
               (Path("x/qbo_write.env"), {k: v for k, v in self.GOOD.items() if k != "QBO_WRITE_REALM_ID"}),
               (loader.MCP_SERVER_DIR / ".env", dict(self.GOOD)),
               (Path("x/.env"), dict(self.GOOD))]
        for path, env in bad:
            with self.subTest(path=str(path)), self.assertRaises(SystemExit):
                loader.validate_env(path, env)

    def test_rotated_refresh_token_is_persisted_without_touching_other_lines(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "qbo_write.env"
            path.write_text("# note\nQBO_WRITE_CLIENT_ID=a\nQBO_WRITE_REFRESH_TOKEN=old\nQBO_WRITE_ENVIRONMENT=sandbox\n", encoding="utf-8")
            loader.set_env_value(path, "QBO_WRITE_REFRESH_TOKEN", "new")
            self.assertEqual(path.read_text(encoding="utf-8"),
                             "# note\nQBO_WRITE_CLIENT_ID=a\nQBO_WRITE_REFRESH_TOKEN=new\nQBO_WRITE_ENVIRONMENT=sandbox\n")


def fake_pnl(monthly, tweak=None):
    """A QBO-shaped monthly P&L containing the three loaded accounts, built from the workbook totals."""
    months = [pd.Timestamp(m) for m in monthly["month"]]
    cols = [{"ColTitle": ""}] + [{"ColTitle": f"{m:%b %Y}"} for m in months] + [{"ColTitle": "Total"}]
    rows = []
    for key, (name, _t, _s) in loader.ACCOUNTS.items():
        vals = [float(loader.cents(v)) for v in monthly[key]]
        if tweak and tweak[0] == key:
            vals[tweak[1]] += tweak[2]
        rows.append({"ColData": [{"value": name}] + [{"value": f"{v:.2f}"} for v in vals] + [{"value": f"{sum(vals):.2f}"}], "type": "Data"})
    return {"Columns": {"Column": cols}, "Rows": {"Row": [{"Header": {"ColData": [{"value": "Group"}]}, "Rows": {"Row": rows}}]}}


class CompareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monthly = loader.load_monthly_totals()

    def test_matching_pnl_has_no_differences(self):
        diffs, names = loader.compare(fake_pnl(self.monthly), self.monthly)
        self.assertEqual(diffs, [])
        self.assertIn(REVENUE, names)

    def test_a_single_wrong_month_is_reported(self):
        diffs, _ = loader.compare(fake_pnl(self.monthly, ("operating_expenses", 5, 12.5)), self.monthly)
        self.assertEqual([(d["metric"], d["month"], d["diff"]) for d in diffs], [("operating_expenses", "2025-06", 12.5)])

    def test_missing_account_is_reported(self):
        pnl = fake_pnl(self.monthly)
        pnl["Rows"]["Row"][0]["Rows"]["Row"].pop(0)
        diffs, _ = loader.compare(pnl, self.monthly)
        self.assertTrue(any("not in the QBO P&L" in d["note"] for d in diffs))


if __name__ == "__main__":
    unittest.main()
