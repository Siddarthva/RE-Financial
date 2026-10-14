"""Write outputs/<client>/qbo_status.json and (with --test) run a read-only QuickBooks CompanyInfo query.

    python 01_connection/qbo_test_connection.py abc          # status only, no network
    python 01_connection/qbo_test_connection.py abc --test   # also call get_company_info over stdio MCP

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
OUT = PROJECT / "outputs"
SERVER = PROJECT / "quickbooks-online-mcp-server" / "dist" / "index.js"
EVIDENCE = Path(__file__).resolve().parent / "evidence" / "quickbooks"
EXAMPLE = Path(__file__).resolve().parent / ".mcp.json.example"
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


SERVER_DIR = "quickbooks-online-mcp-server"
# (code, pattern, what to do). First match wins, so the specific causes come before the generic ones.
DIAGNOSES = (
    ("bad_request", r"input validation|invalid arguments|required at",
     "The test sent a request the server rejects (a bug in this script, not in QuickBooks). Report it; do not re-authorize."),
    ("bad_client", r"invalid_client|client id|client secret|client_id|client_secret",
     f"QuickBooks does not accept the app keys. In {SERVER_DIR}'s environment file check the Development client ID and secret from developer.intuit.com (Keys & credentials), then run 'npm run auth' there."),
    ("expired_token", r"invalid_grant|authorization is invalid or expired|failed to refresh|refresh token|not authenticated|unauthor|401|token (has )?expired",
     f"The refresh token is expired or revoked. In {SERVER_DIR} run 'npm run auth', sign in to the sandbox company in the browser, then retest. Refresh tokens last 100 days and rotate on use."),
    ("wrong_environment", r"production|realm|403|applicationauthorizationfailed|authorizationfault|not authorized",
     f"The token does not match the environment. Set QUICKBOOKS_ENVIRONMENT=sandbox in {SERVER_DIR}'s environment file, use the app's Development keys, and re-run 'npm run auth' with the sandbox company."),
    ("network", r"econnreset|econnrefused|enotfound|etimedout|eai_again|fetch failed|socket hang up|network",
     "The server could not reach quickbooks.api.intuit.com. Check internet access, VPN or proxy, then retest."),
    ("not_configured", r"must be set|missing|enoent|not found|no such file|absolute path",
     f"The server is missing configuration. Check that {SERVER_DIR}'s environment file exists and has the app keys, then run 'npm run auth'."),
    ("rate_or_outage", r"429|5\d\d|servicefault|unavailable|throttl",
     "QuickBooks is rate-limiting or having an outage. Wait a few minutes and retest."),
)


def mask(text: str, limit: int = 160) -> str:
    """Make a server message safe to store: long digit runs (realm IDs) and long token-like strings are removed."""
    text = re.sub(r"\d{6,}", "<N>", text)
    text = re.sub(r"[A-Za-z0-9_\-./+=]{24,}", "<TOKEN>", text)
    return " ".join(text.split())[:limit]


def diagnose(text: str) -> dict:
    """Map a failure text from the server to a cause and a next step. The text itself is stored only after mask()."""
    for code, pattern, advice in DIAGNOSES:
        if re.search(pattern, text, re.I):
            return {"cause": code, "message": advice, "server_said": mask(text)}
    return {"cause": "unknown", "message": f"QuickBooks returned an error that is not recognised. Run 'node dist/index.js' in {SERVER_DIR} from a terminal and read its output.",
            "server_said": mask(text)}


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
                                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", env=env, cwd=SERVER.parents[1])
    except OSError:
        return {**base, "ok": False, "message": "Node.js was not found. Install Node.js and make sure 'node' is on PATH."}
    q: queue.Queue = queue.Queue()
    errq: queue.Queue = queue.Queue()
    threading.Thread(target=_reader, args=(proc.stdout, q), daemon=True).start()
    threading.Thread(target=_reader, args=(proc.stderr, errq), daemon=True).start()
    try:
        _rpc(proc, q, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "close-review-workspace", "version": "1"}}}, 1)
        _rpc(proc, q, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        resp = _rpc(proc, q, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                              "params": {"name": "get_company_info", "arguments": {"params": {}}}}, 2)  # the server wraps every tool's arguments in "params"
    except TimeoutError:
        return {**base, "ok": False, "message": "No response within 45 seconds. Check your network and that the server can start."}
    except (OSError, ValueError):
        stderr = ""
        while not errq.empty():
            stderr += errq.get()
        return {**base, "ok": False, **(diagnose(stderr) if stderr.strip() else {"cause": "server_exited",
                "message": "The QuickBooks MCP server exited unexpectedly. Run 'node dist/index.js' in its folder to see why."})}
    finally:
        proc.kill()
    result = (resp or {}).get("result", {})
    try:
        text = result["content"][0]["text"]
    except (KeyError, IndexError, TypeError):
        text = ""
    # The server reports QuickBooks failures as text starting "Error:" without isError, so check both.
    if "error" in (resp or {}) or result.get("isError") or text.startswith("Error"):
        failure = text or json.dumps((resp or {}).get("error", ""))
        return {**base, "ok": False, **diagnose(failure)}
    try:
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
        "flags_source": "01_connection/.mcp.json.example (template; values enforced on test calls)",
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
