"""Capture the monthly P&L and monthly Balance Sheet for the longest range the sandbox has, redacted, for qbo_adapter.

    python 01_connection/evidence/quickbooks/capture_monthly.py [--start 2024-11-01] [--end 2026-10-31]

Same read-only path as capture_dated.py: starts the MCP server over stdio with QUICKBOOKS_DISABLE_WRITE/UPDATE/DELETE
set to true, calls get_profit_and_loss and get_balance_sheet with summarize_column_by=Month, and passes every response
through redact_and_verify.redact() before anything is written (raw text is never saved). Writes into
evidence/quickbooks/<YYYY-MM-DD>/: NN_name.request.json, NN_name.response.redacted.json and summary.json.
The server reads its own credentials; this script never opens an env file or token store.
Exits 1 if a call fails or a secret-like pattern survives redaction.
"""
import argparse
import json
import queue
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import capture_dated as cd  # noqa: E402  (loads redact_and_verify and qbo_test_connection)

rv, qt = cd.rv, cd.qt


def calls(start: str, end: str):
    common = {"start_date": start, "end_date": end, "summarize_column_by": "Month", "accounting_method": "Accrual"}
    return [("01_pnl_monthly_accrual", "get_profit_and_loss", common),
            ("02_balance_sheet_monthly_accrual", "get_balance_sheet", common)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2024-11-01")
    ap.add_argument("--end", default="2026-10-31")
    args = ap.parse_args(argv)
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
            "protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "evidence-capture-monthly", "version": "1"}}}, 1)
        qt._rpc(proc, q, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        names = sorted(t["name"] for t in qt._rpc(proc, q, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, 2)["result"]["tools"])
        writes = [n for n in names if cd.WRITE_VERBS.search(n)]
        add("Read-only: no create/update/delete tool is registered with the disable flags true", not writes,
            f"{len(names)} tools registered; write-verb tools: {writes or 'none'}")
        for i, (stem, tool, params) in enumerate(calls(args.start, args.end), start=3):
            called_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            resp = qt._rpc(proc, q, {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": tool, "arguments": {"params": params}}}, i)
            content = resp.get("result", {}).get("content", [])
            body = next((c["text"] for c in content if c.get("text", "").lstrip().startswith("{")), "")
            ok = bool(body) and not resp.get("result", {}).get("isError")
            report = rv.redact(json.loads(body), log) if ok else {}
            (out / f"{stem}.request.json").write_text(json.dumps({"server": rv.SERVER, "tool": tool, "params": params, "called_at": called_at}, indent=2), encoding="utf-8")
            (out / f"{stem}.response.redacted.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            cols = [c.get("ColTitle") for c in report.get("Columns", {}).get("Column", [])]
            add(f"{tool} returned a monthly report", ok and len(cols) > 2, f"called_at {called_at}; {len(cols)} columns")
    except (TimeoutError, KeyError, TypeError, ValueError, OSError) as e:
        add("MCP session completed", False, f"{type(e).__name__}: the server did not answer as expected")
    finally:
        proc.kill()
    leaks = sorted({n for p in out.glob("*.json") for n in rv.residual(p.read_text(encoding="utf-8"))})
    add("No secret-like pattern survives redaction (redact_and_verify.residual)", not leaks, f"residual patterns: {leaks or 'none'}")
    (out / "summary.json").write_text(json.dumps({"captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                  "range": [args.start, args.end], "redaction_counts": log, "checks": checks}, indent=2), encoding="utf-8")
    for c in checks:
        print(f"{'PASS' if c['pass'] else 'FAIL'}  {c['claim']}  ({c['detail']})")
    return 0 if all(c["pass"] for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
