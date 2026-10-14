"""Capture a dated, redacted set of read-only QuickBooks checks into evidence/quickbooks/<YYYY-MM-DD>/.

    python 01_connection/evidence/quickbooks/capture_dated.py

Starts the MCP server over stdio with the write/update/delete disable flags set to true (as qbo_test_connection.py
does), then: lists the tools it registers, runs the monthly P&L for Jan-Jun 2026 and the Balance Sheet at
30 Jun 2026. Responses go through redact_and_verify.redact() before anything is written; raw text is never saved.
Writes NN_name.request.json / NN_name.response.redacted.json and summary.json (pass/fail per check, no values
that identify the company). Exits 1 if a check fails or a secret-like pattern survives redaction.
"""
import importlib.util
import json
import queue
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONN = HERE.parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rv = _load("redact_and_verify", HERE / "redact_and_verify.py")
qt = _load("qbo_test_connection", CONN / "qbo_test_connection.py")

CALLS = [
    ("02_pnl_2026-01_to_06_monthly_accrual", "get_profit_and_loss",
     {"start_date": "2026-01-01", "end_date": "2026-06-30", "summarize_column_by": "Month", "accounting_method": "Accrual"}),
    ("03_balance_sheet_2026-06-30", "get_balance_sheet", {"end_date": "2026-06-30", "accounting_method": "Accrual"}),
]
WRITE_VERBS = re.compile(r"(?i)(^|[_-])(create|update|delete|void|send|upload)([_-]|$)")


def summary_value(report, label):
    """Last-column value of the first Summary row whose label matches, e.g. 'TOTAL ASSETS'."""
    for cols in rv.walk_rows(report.get("Rows", {})):
        if cols and cols[0].get("value") == label:
            return rv.money(cols[-1].get("value"))
    return None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if not qt.SERVER.is_file():
        print(qt.test_connection()["message"])
        return 1
    out = HERE / datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out.mkdir(exist_ok=True)
    env = {**qt.os.environ, **{f: "true" for f in qt.FLAGS}}
    proc = subprocess.Popen(["node", str(qt.SERVER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, encoding="utf-8", errors="replace", env=env, cwd=qt.SERVER.parents[1])
    q: queue.Queue = queue.Queue()
    threading.Thread(target=qt._reader, args=(proc.stdout, q), daemon=True).start()
    checks, log = [], {}

    def add(claim, ok, detail):
        checks.append({"claim": claim, "pass": bool(ok), "detail": detail})

    try:
        qt._rpc(proc, q, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "evidence-capture", "version": "1"}}}, 1)
        qt._rpc(proc, q, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        names = sorted(t["name"] for t in qt._rpc(proc, q, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, 2)["result"]["tools"])
        writes = [n for n in names if WRITE_VERBS.search(n)]
        (out / "01_tools_list.response.json").write_text(json.dumps(
            {"server_env": {f: "true" for f in qt.FLAGS}, "tool_count": len(names), "write_tools": writes, "tools": names}, indent=2), encoding="utf-8")
        add("Read-only: no create/update/delete tool is registered with the disable flags true", not writes,
            f"{len(names)} tools registered; write-verb tools: {writes or 'none'}")
        reports = {}
        for i, (stem, tool, params) in enumerate(CALLS, start=3):
            called_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            resp = qt._rpc(proc, q, {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": tool, "arguments": {"params": params}}}, i)
            content = resp.get("result", {}).get("content", [])
            body = next((c["text"] for c in content if c.get("text", "").lstrip().startswith("{")), "")
            ok = bool(body) and not resp.get("result", {}).get("isError")
            reports[tool] = rv.redact(json.loads(body), log) if ok else {}
            (out / f"{stem}.request.json").write_text(json.dumps({"server": rv.SERVER, "tool": tool, "params": params, "called_at": called_at}, indent=2), encoding="utf-8")
            (out / f"{stem}.response.redacted.json").write_text(json.dumps(reports[tool], indent=2), encoding="utf-8")
            add(f"{tool} returned a report", ok, f"called_at {called_at}")
    except (TimeoutError, KeyError, TypeError, ValueError, OSError) as e:
        add("MCP session completed", False, f"{type(e).__name__}: the server did not answer as expected")
    finally:
        proc.kill()

    pnl, bs = reports.get("get_profit_and_loss", {}), reports.get("get_balance_sheet", {})
    cols = [c.get("ColTitle") for c in pnl.get("Columns", {}).get("Column", [])][1:-1]
    add("P&L has one column per month Jan-Jun 2026", cols == [f"{m} 2026" for m in ("Jan", "Feb", "Mar", "Apr", "May", "Jun")], f"columns: {cols}")
    assets, le = summary_value(bs, "TOTAL ASSETS"), summary_value(bs, "TOTAL LIABILITIES AND EQUITY")
    add("Balance Sheet balances at 30 Jun 2026", assets is not None and abs(assets - (le or 0)) < 0.005, f"assets {assets}, liabilities+equity {le}")
    leaks = sorted({n for p in out.glob("*.json") for n in rv.residual(p.read_text(encoding="utf-8"))})
    add("No secret-like pattern survives redaction", not leaks, f"residual patterns: {leaks or 'none'}")
    (out / "summary.json").write_text(json.dumps({"captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                  "redaction_counts": log, "checks": checks}, indent=2), encoding="utf-8")
    for c in checks:
        print(f"{'PASS' if c['pass'] else 'FAIL'}  {c['claim']}  ({c['detail']})")
    return 0 if all(c["pass"] for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
