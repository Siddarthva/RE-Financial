"""PostToolUse hook: after an Edit/Write/MultiEdit of a .py file under src/, run the unit tests.

Exit 2 (stderr = failing test output) tells Claude the edit broke something. Other edits are ignored.
"""
import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    event = json.load(sys.stdin)
    file_path = (event.get("tool_input") or {}).get("file_path")
    if not file_path:
        return 0
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".").resolve()
    try:
        rel = Path(file_path).resolve().relative_to(project)
    except ValueError:
        return 0
    if rel.parts[:1] != ("src",) or rel.suffix != ".py":
        return 0
    run = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=project,
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    tail = (run.stderr or run.stdout).strip().splitlines()[-25:]
    if run.returncode:
        print(f"Unit tests FAILED after editing {rel.as_posix()}:\n" + "\n".join(tail), file=sys.stderr)
        return 2
    print(f"Unit tests passed after editing {rel.as_posix()}: {tail[-1] if tail else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
