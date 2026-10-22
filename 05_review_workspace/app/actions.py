"""Buttons that run the engine's own scripts. No calculation happens here; results are read back via data.py."""
from __future__ import annotations

import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from paths import PROJECT  # noqa: E402


def _run(args: list[str], timeout: int = 180) -> tuple[bool, str]:
    try:
        r = subprocess.run([sys.executable, *args], cwd=PROJECT, capture_output=True, text=True, timeout=timeout, encoding="utf-8")
    except subprocess.TimeoutExpired:
        return False, f"{args[0]} did not finish within {timeout} seconds and was stopped. Run it from a terminal to see its progress."
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Could not start {args[0]}: {type(exc).__name__}"
    text = (r.stdout + r.stderr).strip()
    return r.returncode == 0, text[-1500:]


def run_analysis(client: str, period: str) -> tuple[bool, str]:
    return _run(["scripts/run_pipeline.py", client, period])


def decide(client: str, period: str, reviewer: str, reason: str, reject: bool) -> tuple[bool, str]:
    args = ["scripts/approve.py", client, period, "--reviewer", reviewer, "--reason", reason]
    return _run(args + (["--reject"] if reject else []))


def run_golden_evals() -> tuple[bool, str]:
    return _run(["scripts/export_eval_results.py"], timeout=300)


def test_qbo(client: str) -> tuple[bool, str]:
    return _run(["01_connection/qbo_test_connection.py", client, "--test"], timeout=90)


# ---- full analysis with Claude: `claude -p "/demo-run <client> <period>"` with exactly the command file's allowed tools ----
DEMO_COMMAND = PROJECT / ".claude" / "commands" / "demo-run.md"
CLAUDE_TIMEOUT = 600
_CLIENT, _PERIOD = re.compile(r"^[a-z0-9_-]+$"), re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def claude_path() -> str | None:
    return shutil.which("claude")


def allowed_tools() -> str:
    """The `allowed-tools:` value of .claude/commands/demo-run.md, verbatim."""
    for line in DEMO_COMMAND.read_text(encoding="utf-8").splitlines():
        if line.startswith("allowed-tools:"):
            return line.split(":", 1)[1].strip()
    raise ValueError(f"no allowed-tools line in {DEMO_COMMAND.name}")


def claude_command(client: str, period: str, exe: str = "claude") -> list[str]:
    if not _CLIENT.match(client or "") or not _PERIOD.match(period or ""):
        raise ValueError("client or period is not valid")
    return [exe, "-p", f"/demo-run {client} {period}", "--allowedTools", allowed_tools()]


def _kill(proc) -> None:
    if sys.platform == "win32":  # the npm shim is a .cmd: kill its children too
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    proc.kill()


def run_claude(client: str, period: str, on_line=None, timeout: int = CLAUDE_TIMEOUT) -> tuple[str, str]:
    """Run the full analysis from the repo root. Returns (status, log); status is ok, failed, timeout or error."""
    exe = claude_path()
    if not exe:
        return "error", "The claude CLI was not found on PATH."
    try:
        cmd = claude_command(client, period, exe)
        proc = subprocess.Popen(cmd, cwd=PROJECT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    except (OSError, ValueError) as exc:
        return "error", f"Could not start claude: {type(exc).__name__}: {exc}"
    lines: queue.Queue = queue.Queue()

    def pump():
        for ln in proc.stdout:
            lines.put(ln)
        lines.put(None)

    threading.Thread(target=pump, daemon=True).start()
    log, deadline = [], time.monotonic() + timeout
    while True:
        try:
            ln = lines.get(timeout=0.25)
        except queue.Empty:
            if time.monotonic() > deadline:
                _kill(proc)
                return "timeout", "".join(log)
            continue
        if ln is None:
            break
        log.append(ln)
        if on_line:
            on_line("".join(log))
        if time.monotonic() > deadline:
            _kill(proc)
            return "timeout", "".join(log)
    try:
        code = proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        _kill(proc)
        return "timeout", "".join(log)
    return ("ok" if code == 0 else "failed"), "".join(log)
