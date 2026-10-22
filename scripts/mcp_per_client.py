"""Start one stdio QuickBooks MCP server process per client, each with its own credential file, working dir and token store.

    python scripts/mcp_per_client.py --clients abc qbo_sandbox --secrets-root C:/RE/.secrets/clients --check
    python scripts/mcp_per_client.py --clients abc --secrets-root DIR --server node path/to/dist/index.js   # stays up

For client <id> the server process gets:
- QUICKBOOKS_TOKEN_STORE_PATH = <secrets-root>/<id>/qbo.env  (the server's own env file and token store; passed by
  NAME only, this script never opens, reads or copies it);
- working dir <runtime-root>/<id>/ (created if missing);
- QUICKBOOKS_DISABLE_WRITE/UPDATE/DELETE = true (forced; cannot be overridden from the parent environment);
- no QUICKBOOKS_* variable inherited from the parent, so one client's credentials cannot leak into another's process.

--check sends the MCP initialize handshake to every process, prints one row per client and stops them.
This is per-client process separation on one machine. It is not a network service: nothing here listens on a port.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_SERVER = ["node", str(PROJECT / "quickbooks-online-mcp-server" / "dist" / "index.js")]
FLAGS = ("QUICKBOOKS_DISABLE_WRITE", "QUICKBOOKS_DISABLE_UPDATE", "QUICKBOOKS_DISABLE_DELETE")
CLIENT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")  # same rule as run_client.CLIENT_ID
ENV_FILE_NAME = "qbo.env"


def plan(client: str, secrets_root: Path, runtime_root: Path) -> dict:
    """Paths for one client. Pure: builds names, opens nothing."""
    if not CLIENT_ID.match(client):
        raise ValueError(f"Invalid client id {client!r}; use lowercase letters, digits, '-' or '_'.")
    token_dir = Path(secrets_root) / client
    return {"client": client, "workdir": Path(runtime_root) / client, "token_dir": token_dir,
            "token_store_path": token_dir / ENV_FILE_NAME}


def child_env(p: dict, base: dict | None = None) -> dict:
    """Parent environment minus every QUICKBOOKS_* variable, plus this client's store path and the read-only flags."""
    env = {k: v for k, v in (os.environ if base is None else base).items() if not k.upper().startswith("QUICKBOOKS_")}
    env["QUICKBOOKS_TOKEN_STORE_PATH"] = str(p["token_store_path"])
    env.update({f: "true" for f in FLAGS})
    env["MCP_CLIENT_ID"] = p["client"]
    return env


def start(p: dict, server: list[str]) -> subprocess.Popen:
    p["workdir"].mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(server, cwd=p["workdir"], env=child_env(p), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace")


def handshake(proc: subprocess.Popen, timeout: float = 45) -> dict:
    msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "mcp-per-client", "version": "1"}}}
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    import threading
    box: dict = {}

    def read():
        for line in proc.stdout:
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if obj.get("id") == 1:
                box["resp"] = obj
                return
    t = threading.Thread(target=read, daemon=True)
    t.start()
    t.join(timeout)
    if "resp" not in box:
        raise TimeoutError("no initialize response")
    return box["resp"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clients", nargs="+", required=True)
    ap.add_argument("--secrets-root", type=Path, required=True, help="folder holding <client>/qbo.env (outside the repo)")
    ap.add_argument("--runtime-root", type=Path, default=PROJECT / "outputs" / "_mcp_runtime")
    ap.add_argument("--server", nargs=argparse.REMAINDER, help="server command (default: node <clone>/dist/index.js)")
    ap.add_argument("--check", action="store_true", help="handshake with each process, print a table, stop them")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    server = args.server or DEFAULT_SERVER
    plans = [plan(c, args.secrets_root, args.runtime_root) for c in args.clients]
    if len({str(p["token_store_path"]) for p in plans}) != len(plans):
        print("ERROR: two clients resolve to the same token store.")
        return 2
    procs = [(p, start(p, server)) for p in plans]
    rc = 0
    try:
        print("| client | pid | working dir | token store (path only, not opened) | initialize |\n|---|---|---|---|---|")
        for p, proc in procs:
            status = "running"
            if args.check:
                try:
                    resp = handshake(proc)
                    status = "ok" if "result" in resp else f"error: {resp.get('error', {}).get('message', '?')}"
                except (TimeoutError, OSError) as exc:
                    status, rc = f"failed: {type(exc).__name__}", 1
            print(f"| {p['client']} | {proc.pid} | {p['workdir']} | {p['token_store_path']} | {status} |", flush=True)
        if not args.check:
            for _, proc in procs:
                proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for _, proc in procs:
            proc.kill()
    return rc


if __name__ == "__main__":
    sys.exit(main())
