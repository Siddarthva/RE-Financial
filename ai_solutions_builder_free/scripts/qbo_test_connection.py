"""Write outputs/<client>/qbo_status.json and (with --test) run a read-only QuickBooks CompanyInfo query.

    python scripts/qbo_test_connection.py abc          # status only, no network
    python scripts/qbo_test_connection.py abc --test   # also call get_company_info over stdio MCP

Read-only: the server is started with the write/update/delete disable flags set to true, and only the
get_company_info tool is called. Credentials stay in the server's own environment; this script never
reads them and never prints server output, tokens or realm IDs - only fixed, actionable messages.
"""
from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT.parent / "outputs"
SERVER = PROJECT.parent / "quickbooks-online-mcp-server" / "dist" / "index.js"
EVIDENCE = PROJECT / "evidence" / "quickbooks"
EXAMPLE = PROJECT / ".mcp.json.example"
FLAGS = ("QUICKBOOKS_DISABLE_WRITE", "QUICKBOOKS_DISABLE_UPDATE", "QUICKBOOKS_DISABLE_DELETE")


def declared_flags() -> dict:
    try:
        env = json.loads(EXAMPLE.read_text(encoding="utf-8"))["mcpServers"]["quickbooks"]["env"]
        return {f: env.get(f) for f in FLAGS}
    except (OSError, ValueError, KeyError):
        return {f: None for f in FLAGS}


def last_retrieval() -> str | None:
    dates = []
    for p in EVIDENCE.glob("*.request.json"):
        try:
            m = re.match(r"\d{4}-\d{2}-\d{2}", json.loads(p.read_text(encoding="utf-8")).get("called_at", ""))
        except (OSError, ValueError):
            continue
        if m:
            dates.append(m.group(0))
    return max(dates) if dates else None


def _reader(stream, q):
    for line in iter(stream.readline, ""):
        q.put(line)


def _rpc(proc, q, msg, want_id=None, timeout=45):
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    if want_id is None:
        return None
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            line = q.get(timeout=1)
        except queue.Empty:
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if data.get("id") == want_id:
            return data
    raise TimeoutError


def test_connection() -> dict:
    base = {"tested_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if not SERVER.is_file():
        return {**base, "ok": False, "message": "QuickBooks MCP server is not built. Run 'npm run build' in quickbooks-online-mcp-server."}
    env = {**os.environ, **{f: "true" for f in FLAGS}}
    try:
        proc = subprocess.Popen(["node", str(SERVER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env=env, cwd=SERVER.parents[1])
    except OSError:
        return {**base, "ok": False, "message": "Node.js was not found. Install Node.js and make sure 'node' is on PATH."}
    q: queue.Queue = queue.Queue()
    threading.Thread(target=_reader, args=(proc.stdout, q), daemon=True).start()
    try:
        _rpc(proc, q, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "close-review-workspace", "version": "1"}}}, 1)
        _rpc(proc, q, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        resp = _rpc(proc, q, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                              "params": {"name": "get_company_info", "arguments": {}}}, 2)
    except TimeoutError:
        return {**base, "ok": False, "message": "No response within 45 seconds. Check your network and that the server can start."}
    except (OSError, ValueError):
        return {**base, "ok": False, "message": "The QuickBooks MCP server exited unexpectedly. Run it once from a terminal to see why."}
    finally:
        proc.kill()
    blob = json.dumps(resp or {})
    if "error" in (resp or {}) or (resp or {}).get("result", {}).get("isError"):
        if re.search(r"401|auth|token|invalid_grant|refresh|unauthor", blob, re.I):
            msg = "QuickBooks rejected the credentials. Re-authorize the app (new refresh token) and try again."
        else:
            msg = "QuickBooks returned an error. Details are withheld; check the server's own logs."
        return {**base, "ok": False, "message": msg}
    try:
        text = resp["result"]["content"][0]["text"]
        name = (json.loads(text).get("CompanyName") or json.loads(text).get("CompanyInfo", {}).get("CompanyName"))
    except (KeyError, IndexError, ValueError, AttributeError):
        name = None
    return {**base, "ok": True, "company_name": name, "message": "Connected. Read-only CompanyInfo query succeeded."}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    client = sys.argv[1]
    if not re.match(r"^[a-z0-9][a-z0-9_-]{0,63}$", client):
        return 2
    d = OUT / client
    d.mkdir(parents=True, exist_ok=True)
    path = d / "qbo_status.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    status = {
        "method": "Official Intuit MCP server, stdio, read-only", "flags": declared_flags(),
        "flags_source": ".mcp.json.example (template; values enforced on test calls)",
        "last_successful_retrieval": last_retrieval(), "last_test": old.get("last_test"),
    }
    if "--test" in sys.argv:
        status["last_test"] = test_connection()
        with open(d / "audit_log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": status["last_test"]["tested_at"], "event": "qbo_test_connection",
                                "client": client, "actor": "workspace", "status": "ok" if status["last_test"]["ok"] else "failed"}) + "\n")
    path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(json.dumps(status["last_test"] or {"message": "status refreshed"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
