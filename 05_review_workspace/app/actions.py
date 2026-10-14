"""Buttons that run the engine's own scripts. No calculation happens here; results are read back via data.py."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from paths import PROJECT  # noqa: E402


def _run(args: list[str], timeout: int = 180) -> tuple[bool, str]:
    try:
        r = subprocess.run([sys.executable, *args], cwd=PROJECT, capture_output=True, text=True, timeout=timeout, encoding="utf-8")
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Could not start script: {type(exc).__name__}"
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
