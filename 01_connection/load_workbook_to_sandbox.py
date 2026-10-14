"""Load ABC's monthly totals into the QuickBooks *sandbox* as journal entries, and compare QBO with the workbook.

    python 01_connection/load_workbook_to_sandbox.py --dry-run                 # default: print the plan, write nothing
    python 01_connection/load_workbook_to_sandbox.py --apply                   # create missing journal entries
    python 01_connection/load_workbook_to_sandbox.py --compare PNL.json        # QBO monthly P&L vs the workbook analysis

This is a separate write path. It never touches the read-only MCP server or its config (`.env`, the
QUICKBOOKS_DISABLE_* flags). It reads its own credentials from a write-scoped env file, kept outside the repo:

    QBO_WRITE_CLIENT_ID, QBO_WRITE_CLIENT_SECRET, QBO_WRITE_REFRESH_TOKEN, QBO_WRITE_REALM_ID,
    QBO_WRITE_ENVIRONMENT=sandbox          (anything else is refused)

One journal entry per month, DocNumber ABC-YYYY-MM, dated month end, three lines (Total Income, Total COGS,
Total Operating Expenses) plus a balancing line to a clearing account, so each entry's net effect on the P&L equals
that month's workbook net income. Opex detail (70 accounts) and the Balance Sheet are NOT loaded.

Idempotent: an entry whose DocNumber already exists is skipped if its lines match, reported as a CONFLICT if they
differ (nothing is updated or deleted). Accounts are found by name before being created.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
import abc_workbook_adapter as engine  # noqa: E402
import run_client  # noqa: E402
from client_sandbox import client_sandbox  # noqa: E402

CLIENT = "abc"
DEFAULT_ENV_FILE = PROJECT / ".secrets" / "qbo_write.env"
MCP_SERVER_DIR = PROJECT / "quickbooks-online-mcp-server"
REQUIRED_ENV = ("QBO_WRITE_CLIENT_ID", "QBO_WRITE_CLIENT_SECRET", "QBO_WRITE_REFRESH_TOKEN", "QBO_WRITE_REALM_ID")
API = "https://sandbox-quickbooks.api.intuit.com/v3/company"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
MINOR_VERSION = "75"
NOTE_PREFIX = "workbook-load:v1"

# (key, QBO account name, QBO account type, posting side when the amount is positive)
ACCOUNTS = {
    "revenue": ("Workbook Load - Total Income", "Income", "Credit"),
    "cost_of_goods_sold": ("Workbook Load - Total COGS", "Cost of Goods Sold", "Debit"),
    "operating_expenses": ("Workbook Load - Total Operating Expenses", "Expense", "Debit"),
}
CLEARING = ("Workbook Load - Clearing", "Other Current Liability")


def cents(x) -> Decimal:
    return Decimal(str(round(float(x), 2))).quantize(Decimal("0.01"))


# ---------------------------------------------------------------- plan (no network)

def load_monthly_totals(clients_root=run_client.CLIENTS_ROOT, outputs_root=run_client.OUTPUTS_ROOT):
    with client_sandbox(CLIENT, clients_root, outputs_root):
        cfg = run_client.load_config(CLIENT, clients_root)
        layout = {"sheet": cfg["sheets"]["income_statement"], "header_label": cfg["layout"]["header_label"],
                  "month_format": cfg["layout"]["month_format"],
                  "sections": {sid: (v["header"], v["total"]) for sid, v in cfg["sections"].items()}}
        monthly = engine.build_monthly_summary(engine.parse_wide_income_statement(cfg["workbook_path"], layout), cfg["totals"])
    return monthly


def build_entry(month: pd.Timestamp, totals: dict) -> dict:
    """Balanced journal entry for one month. Negative buckets post on the opposite side; the plug goes to clearing."""
    lines, debit, credit = [], Decimal(0), Decimal(0)
    for key, (name, _type, side) in ACCOUNTS.items():
        amount = cents(totals[key])
        if amount == 0:
            continue
        posting = side if amount > 0 else ("Credit" if side == "Debit" else "Debit")
        lines.append({"account": name, "posting": posting, "amount": abs(amount), "description": f"{key} {month:%Y-%m} (workbook total)"})
        debit += abs(amount) if posting == "Debit" else 0
        credit += abs(amount) if posting == "Credit" else 0
    plug = debit - credit
    if plug != 0:
        lines.append({"account": CLEARING[0], "posting": "Credit" if plug > 0 else "Debit", "amount": abs(plug),
                      "description": f"balancing line {month:%Y-%m} (equals workbook net {'loss' if plug > 0 else 'income'})"})
    signature = hashlib.sha256(json.dumps([(l["account"], l["posting"], str(l["amount"])) for l in lines]).encode()).hexdigest()[:16]
    return {"doc_number": f"{CLIENT.upper()}-{month:%Y-%m}", "txn_date": f"{(month + pd.offsets.MonthEnd(0)):%Y-%m-%d}",
            "lines": lines, "signature": signature, "private_note": f"{NOTE_PREFIX} sha256:{signature} source: ABC Inc workbook, {month:%Y-%m}"}


def build_plan(monthly, start=None, end=None) -> list[dict]:
    plan = []
    for row in monthly.itertuples():
        month = pd.Timestamp(row.month)
        if (start and month < pd.Timestamp(start + "-01")) or (end and month > pd.Timestamp(end + "-01")):
            continue
        entry = build_entry(month, {k: getattr(row, k) for k in ACCOUNTS})
        debits = sum(l["amount"] for l in entry["lines"] if l["posting"] == "Debit")
        credits = sum(l["amount"] for l in entry["lines"] if l["posting"] == "Credit")
        assert debits == credits, entry
        entry["net_income_workbook"] = cents(row.net_income)
        plan.append(entry)
    return plan


# ---------------------------------------------------------------- credentials

def read_env_file(path: Path) -> dict:
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def validate_env(path: Path, env: dict):
    """Refuse anything that is not a separate, sandbox-only, complete write env file."""
    resolved = Path(path).resolve()
    mcp_env = (MCP_SERVER_DIR / ".env").resolve()
    if resolved == mcp_env or resolved.name == ".env":
        raise SystemExit("Refusing to use the read-only MCP server's .env. Use a separate write-scoped env file.")
    missing = [k for k in REQUIRED_ENV if not env.get(k)]
    if missing:
        raise SystemExit(f"{path}: missing {missing}")
    if env.get("QBO_WRITE_ENVIRONMENT", "").lower() != "sandbox":
        raise SystemExit(f"{path}: QBO_WRITE_ENVIRONMENT must be 'sandbox'. This script never writes to production.")


def set_env_value(path: Path, key: str, value: str):
    """Persist a rotated refresh token: replace the key's line, keep everything else, write atomically."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    out = [f"{key}={value}" if l.split("=", 1)[0].strip() == key else l for l in lines]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------- QBO REST (sandbox only)

class QboApi:
    def __init__(self, env: dict, env_path: Path):
        self.env, self.env_path, self.realm, self.token = env, Path(env_path), env["QBO_WRITE_REALM_ID"], None

    def _http(self, req):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:600]
            raise RuntimeError(f"QBO HTTP {exc.code} for {req.get_method()} {req.full_url.split('?')[0]}: {detail}") from None

    def refresh(self):
        basic = base64.b64encode(f"{self.env['QBO_WRITE_CLIENT_ID']}:{self.env['QBO_WRITE_CLIENT_SECRET']}".encode()).decode()
        body = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": self.env["QBO_WRITE_REFRESH_TOKEN"]}).encode()
        data = self._http(urllib.request.Request(TOKEN_URL, data=body, method="POST", headers={
            "Authorization": f"Basic {basic}", "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}))
        self.token = data["access_token"]
        if data.get("refresh_token") and data["refresh_token"] != self.env["QBO_WRITE_REFRESH_TOKEN"]:
            set_env_value(self.env_path, "QBO_WRITE_REFRESH_TOKEN", data["refresh_token"])  # Intuit rotates it; keep the new one
            self.env["QBO_WRITE_REFRESH_TOKEN"] = data["refresh_token"]

    def request(self, method, path, body=None, query=None):
        if self.token is None:
            self.refresh()
        url = f"{API}/{self.realm}/{path}?" + urllib.parse.urlencode({"minorversion": MINOR_VERSION, **(query or {})})
        return self._http(urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None, headers={
            "Authorization": f"Bearer {self.token}", "Accept": "application/json", "Content-Type": "application/json"}))

    def query(self, sql):
        return self.request("GET", "query", query={"query": sql}).get("QueryResponse", {})


def find_account(api, name):
    found = api.query(f"select * from Account where Name = '{name}'").get("Account", [])
    return found[0] if found else None


def ensure_accounts(api, apply: bool) -> dict:
    """Account ids by name; creates missing ones only when apply is true (None marks 'would create')."""
    ids = {}
    for name, acct_type in [(v[0], v[1]) for v in ACCOUNTS.values()] + [CLEARING]:
        acct = find_account(api, name)
        if acct is None and apply:
            acct = api.request("POST", "account", {"Name": name, "AccountType": acct_type})["Account"]
        ids[name] = acct["Id"] if acct else None
    return ids


def run_plan(plan, api, ids, apply: bool) -> list[dict]:
    """Per entry: create / skip (already loaded, same lines) / conflict (exists, different) -- never update or delete."""
    results = []
    by_id = {v: k for k, v in ids.items() if v}
    for e in plan:
        existing = api.query(f"select * from JournalEntry where DocNumber = '{e['doc_number']}'").get("JournalEntry", [])
        if existing:
            got = sorted((by_id.get(l["JournalEntryLineDetail"]["AccountRef"]["value"], l["JournalEntryLineDetail"]["AccountRef"].get("name", "?")),
                          l["JournalEntryLineDetail"]["PostingType"], str(cents(l["Amount"]))) for l in existing[0]["Line"]
                         if l.get("DetailType") == "JournalEntryLineDetail")
            want = sorted((l["account"], l["posting"], str(l["amount"])) for l in e["lines"])
            results.append({"doc": e["doc_number"], "action": "skip" if got == want else "CONFLICT", "detail": "already loaded" if got == want else f"remote {got} != workbook {want}"})
            continue
        if not apply:
            results.append({"doc": e["doc_number"], "action": "would create", "detail": ""})
            continue
        body = {"DocNumber": e["doc_number"], "TxnDate": e["txn_date"], "PrivateNote": e["private_note"], "Line": [
            {"Description": l["description"], "Amount": float(l["amount"]), "DetailType": "JournalEntryLineDetail",
             "JournalEntryLineDetail": {"PostingType": l["posting"], "AccountRef": {"value": ids[l["account"]]}}} for l in e["lines"]]}
        created = api.request("POST", "journalentry", body)["JournalEntry"]
        results.append({"doc": e["doc_number"], "action": "created", "detail": f"id {created['Id']}"})
    return results


# ---------------------------------------------------------------- compare QBO P&L with the workbook

def parse_qbo_pnl(pnl: dict) -> dict:
    """{account name: {'YYYY-MM': amount}} for every data/summary row of a QBO monthly P&L report."""
    cols = [c["ColTitle"] for c in pnl["Columns"]["Column"]]
    months = {i: pd.to_datetime(t, format="%b %Y").strftime("%Y-%m") for i, t in enumerate(cols) if t and t != "Total" and i > 0}
    found = {}

    def walk(rows):
        for r in rows:
            for part in (r.get("Header"), r.get("Summary"), r if "ColData" in r else None):
                if part and part.get("ColData"):
                    cd = part["ColData"]
                    found[cd[0]["value"]] = {months[i]: float(cd[i]["value"] or 0) for i in months if i < len(cd)}
            walk(r.get("Rows", {}).get("Row", []))
    walk(pnl["Rows"]["Row"])
    return found


def compare(pnl: dict, monthly) -> tuple[list[dict], list[str]]:
    qbo = parse_qbo_pnl(pnl)
    diffs = []
    for key, (name, _t, _s) in ACCOUNTS.items():
        remote = qbo.get(name)
        if remote is None:
            diffs.append({"metric": key, "month": "all", "workbook": None, "qbo": None, "diff": None, "note": f"account '{name}' not in the QBO P&L"})
            continue
        for row in monthly.itertuples():
            m = f"{pd.Timestamp(row.month):%Y-%m}"
            if m not in remote:
                continue  # the P&L was run for a narrower period
            wb, q = float(cents(getattr(row, key))), remote[m]
            if abs(wb - q) > 0.005:
                diffs.append({"metric": key, "month": m, "workbook": wb, "qbo": q, "diff": round(q - wb, 2), "note": ""})
    return diffs, sorted(qbo)


STRUCTURAL = [
    "Operating expenses are one line in QBO (3 loaded accounts): the workbook's 70 expense accounts, categories, one-off detection and top movements cannot be reproduced from QBO.",
    "Gross profit, operating income and net income are derived in QBO from the three loaded accounts and equal the workbook only if those totals tie.",
    "The sandbox company has its own sample transactions (from May 2026); compare only the 'Workbook Load - ...' accounts, never the company total.",
    "The Balance Sheet, cash and runway are not loaded; the clearing account carries the cumulative net result and has no workbook counterpart.",
    "TTM and month-over-month figures need 12 and 2 loaded months respectively; a partial load withholds them exactly as the workbook analysis does.",
]


# ---------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="show the plan; create nothing (default)")
    mode.add_argument("--apply", action="store_true", help="create the missing accounts and journal entries in the sandbox")
    mode.add_argument("--compare", type=Path, metavar="PNL_JSON", help="compare a saved QBO monthly P&L (summarize by Month) with the workbook")
    ap.add_argument("--env-file", type=Path, default=Path(os.environ.get("QBO_WRITE_ENV_FILE", DEFAULT_ENV_FILE)))
    ap.add_argument("--from", dest="start", metavar="YYYY-MM"), ap.add_argument("--to", dest="end", metavar="YYYY-MM")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    for flag, v in (("--from", args.start), ("--to", args.end)):
        if v is not None and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", v):
            ap.error(f"{flag} must look like 2026-06, got {v!r}")
    if args.start and args.end and args.start > args.end:
        ap.error(f"--from {args.start} is after --to {args.end}")
    if args.apply and not args.env_file.exists():  # fail before any file or network side effect
        raise SystemExit(f"--apply needs the write-scoped env file: {args.env_file} (not found; nothing was changed)")
    monthly = load_monthly_totals()
    out_dir = run_client.OUTPUTS_ROOT / CLIENT

    if args.compare:
        try:
            pnl = json.loads(args.compare.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise SystemExit(f"--compare file not found: {args.compare}. Save a QBO monthly P&L first "
                             "(01_connection/evidence/quickbooks/capture_dated.py).")
        except ValueError:
            raise SystemExit(f"--compare file is not valid JSON: {args.compare}. Use the redacted P&L response saved by capture_dated.py.")
        diffs, names = compare(pnl, monthly)
        lines = ["# QBO vs workbook", "", f"QBO P&L: `{args.compare.name}`. Workbook: ABC monthly totals.", ""]
        lines += ["No differences in the three loaded accounts." if not diffs else "| Metric | Month | Workbook | QBO | QBO - workbook | Note |\n|---|---|---|---|---|---|"]
        lines += [f"| {d['metric']} | {d['month']} | {d['workbook']} | {d['qbo']} | {d['diff']} | {d['note']} |" for d in diffs]
        lines += ["", "## Structural differences (by design)", ""] + [f"- {s}" for s in STRUCTURAL]
        (out_dir / "qbo_vs_workbook.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 1 if diffs else 0

    plan = build_plan(monthly, args.start, args.end)
    if not plan:  # never replace a saved plan with an empty one
        raise SystemExit(f"No workbook months between {args.start or 'the start'} and {args.end or 'the end'} "
                         f"(workbook: {pd.Timestamp(monthly['month'].min()):%Y-%m} to {pd.Timestamp(monthly['month'].max()):%Y-%m}); nothing was written.")
    print(f"{'APPLY' if args.apply else 'DRY RUN'}: {len(plan)} journal entries, Jan 2025-Jun 2026 workbook totals (sandbox only)\n")
    print(f"{'Doc':<12}{'Date':<12}{'Income':>14}{'COGS':>14}{'Opex':>16}{'Clearing':>16}  Net income (workbook)")
    for e in plan:
        side = {l["account"]: (l["amount"] if l["posting"] == "Debit" else -l["amount"]) for l in e["lines"]}
        print(f"{e['doc_number']:<12}{e['txn_date']:<12}{-side.get(ACCOUNTS['revenue'][0], 0):>14,.2f}{side.get(ACCOUNTS['cost_of_goods_sold'][0], 0):>14,.2f}"
              f"{side.get(ACCOUNTS['operating_expenses'][0], 0):>16,.2f}{side.get(CLEARING[0], 0):>16,.2f}  {e['net_income_workbook']:>14,.2f}")
    plan_path = out_dir / "qbo_load_plan.json"
    plan_path.write_text(json.dumps([{**e, "lines": [{**l, "amount": str(l["amount"])} for l in e["lines"]], "net_income_workbook": str(e["net_income_workbook"])} for e in plan], indent=2), encoding="utf-8")
    print(f"\nPlan saved: {plan_path}")

    if not args.env_file.exists():
        if args.apply:
            raise SystemExit(f"--apply needs the write-scoped env file: {args.env_file} (not found; nothing was changed)")
        print(f"Env file not found ({args.env_file}); remote status not checked. Every entry would be created.")
        return 0
    env = read_env_file(args.env_file)
    validate_env(args.env_file, env)
    api = QboApi(env, args.env_file)
    company = api.request("GET", f"companyinfo/{api.realm}")["CompanyInfo"]
    print(f"Connected to sandbox company: {company.get('CompanyName')}")
    ids = ensure_accounts(api, args.apply)
    for r in run_plan(plan, api, ids, args.apply):
        print(f"  {r['doc']:<12}{r['action']:<14}{r['detail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
