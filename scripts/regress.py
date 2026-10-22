"""One command to answer "did my change break anything?". Run it before every commit.

    python scripts/regress.py            # full: unit -> golden -> commentary -> trigger -> guards -> mutation -> fault injection
    python scripts/regress.py --fast     # skips mutation and fault injection (about 3 min instead of about 30)
    python scripts/regress.py --live     # additionally routes every trigger case through `claude -p` (costs model calls)
    python scripts/regress.py --only unit golden     # run just these layers (names below)

Layers, in order: unit, golden, commentary (the flawed control must FAIL), trigger, guards, mutation, faults.
Last guard: `render_counts.py --check` against this run's results (the README count tables must match them).
Prints a summary table, writes outputs/regress_results.json, exits 1 if any check regressed, 0 if all held.
Nothing here edits an expected value: each check is a call to the existing eval, and its exit code is the verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-X", "utf8"]
WORKBOOK = ROOT / "data" / "ABC Inc - Financial Statements.xlsx"
WORKBOOK_SHA = "75da8d679a89551f9e46b3563b7cfc724d9aaeabe0444b0214d455a0b335a0ea"  # same constant as fault_injection.py
RESULTS = ROOT / "outputs" / "regress_results.json"
COMMENTARY = ["03_evals/grade_commentary.py"]
# (layer, name, command, expected, detail regex, slow)
# expected: "pass" = exit 0 is required; "fail" = a NEGATIVE CONTROL, exit 1 is required (exit 0 means the grader went blind).
CHECKS = [
    ("unit", "unit tests", PY + ["-m", "unittest", "discover", "-s", "tests"], "pass", r"Ran (\d+) tests?", False),
    ("golden", "golden cases", PY + ["03_evals/run_golden_evals.py"], "pass", r"Score: (\d+/\d+)", False),
    ("commentary", "engine commentary", PY + COMMENTARY, "pass", r"RESULT: (\w+)", False),
    ("commentary", "reviewed commentary (abc 2026-06)", PY + COMMENTARY + ["--commentary", "outputs/abc/commentary_2026-06.md"], "pass", r"RESULT: (\w+)", False),
    ("commentary", "saved skill output", PY + COMMENTARY + ["--commentary", "outputs/skill_commentary.md"], "pass", r"RESULT: (\w+)", False),
    ("commentary", "FLAWED CONTROL must fail", PY + COMMENTARY + ["--commentary", "outputs/abc/commentary_2026-06_flawed_control.md"], "fail", r"RESULT: (\w+)", False),
    ("commentary", "flux-explanations grader", PY + ["03_evals/grade_workflow_skills.py", "flux", "abc", "2026-06"], "pass", r"(PASS|FAIL)", False),
    ("commentary", "client-questions grader", PY + ["03_evals/grade_workflow_skills.py", "questions", "abc", "2026-06"], "pass", r"(PASS|FAIL)", False),
    ("trigger", "trigger cases (structure)", PY + ["03_evals/run_trigger_evals.py"], "pass", r"(\d+ entries, \d+ problems)", False),
    ("guards", "internal links", PY + ["scripts/check_links.py"], "pass", r"(\d+ files, \d+ links, \d+ broken)", False),
    ("mutation", "mutation test (25 injected bugs)", PY + ["03_evals/mutation_test.py"], "pass", r"(\d+/\d+) mutants caught", True),
    ("faults", "fault injection (42 corrupted workbooks)", PY + ["03_evals/robustness/fault_injection.py"], "pass", r"(\d+/\d+) faults behaved", True),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def secret_scan() -> tuple[int, str]:
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
    bad = 0
    for i in range(0, len(files), 100):  # chunk: Windows limits the command line length
        p = subprocess.run(PY + ["scripts/scan_secrets.py"] + files[i:i + 100], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        bad += p.returncode != 0
    return (1 if bad else 0), f"{len(files)} tracked files, {'findings in ' + str(bad) + ' chunk(s)' if bad else '0 findings'}"


def run_check(layer, name, cmd, expected, regex, live=False):
    if live and name.startswith("trigger"):
        cmd = cmd + ["--live"]
        name += " + live routing"
    t0 = time.monotonic()
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    text = p.stdout + "\n" + p.stderr
    m = re.findall(regex, text)
    detail = m[-1] if m else f"exit {p.returncode}"
    ok = (p.returncode == 0) if expected == "pass" else (p.returncode == 1)  # a control that crashes (exit 2+) is not a clean FAIL
    if expected == "fail":
        detail += " (failed, as it must)" if ok else " (DID NOT FAIL: the grader no longer detects a known-bad text)"
    return {"layer": layer, "check": name, "ok": ok, "detail": str(detail), "seconds": round(time.monotonic() - t0, 1),
            "tail": "" if ok else text.strip()[-600:]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fast", action="store_true", help="skip mutation and fault injection")
    ap.add_argument("--live", action="store_true", help="also route trigger cases through `claude -p`")
    ap.add_argument("--only", nargs="+", metavar="LAYER", help="run only these layers")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    started = datetime.now(timezone.utc)
    before = sha(WORKBOOK) if WORKBOOK.is_file() else None
    results = []
    for layer, name, cmd, expected, regex, slow in CHECKS:
        if (args.fast and slow) or (args.only and layer not in args.only):
            continue
        print(f"... {layer}: {name}", flush=True)
        r = run_check(layer, name, cmd, expected, regex, args.live)
        results.append(r)
        print(f"    {'ok' if r['ok'] else 'REGRESSION'}  {r['detail']}  ({r['seconds']}s)", flush=True)
    if not args.only or "guards" in args.only:
        t0 = time.monotonic()
        code, detail = secret_scan()
        results.append({"layer": "guards", "check": "secret scan", "ok": code == 0, "detail": detail, "seconds": round(time.monotonic() - t0, 1), "tail": ""})
        after = sha(WORKBOOK) if WORKBOOK.is_file() else None
        results.append({"layer": "guards", "check": "source workbook unchanged", "ok": before == after == WORKBOOK_SHA,
                        "detail": f"sha256 {str(after)[:12]}…", "seconds": 0.0, "tail": ""})
    skipped = [n for _, n, _, _, _, slow in CHECKS if slow and args.fast]
    sha_now = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    RESULTS.parent.mkdir(exist_ok=True)

    def write_results():
        failed = [r for r in results if not r["ok"]]
        RESULTS.write_text(json.dumps({"started": started.isoformat(timespec="seconds"), "git_head": sha_now, "mode": "fast" if args.fast else "full",
                                       "all_held": not failed, "skipped": skipped, "results": results}, indent=2), encoding="utf-8")

    if any(r["check"] == "unit tests" for r in results) and (not args.only or "guards" in args.only):
        write_results()  # render_counts reads the unit count from this file, so it must hold this run's result first
        results.append(run_check("guards", "doc counts (render_counts --check)", PY + ["scripts/render_counts.py", "--check"], "pass", r"(\d+ blocks, \d+ stale)"))
        print(f"    {'ok' if results[-1]['ok'] else 'REGRESSION'}  doc counts: {results[-1]['detail']}", flush=True)
    print("\n| Layer | Check | Result | Detail | Time |\n|---|---|---|---|---|")
    for r in results:
        print(f"| {r['layer']} | {r['check']} | {'ok' if r['ok'] else '**REGRESSION**'} | {r['detail']} | {r['seconds']}s |")
    for n in skipped:
        print(f"| - | {n} | skipped (--fast) | | |")
    failed = [r for r in results if not r["ok"]]
    for r in failed:
        print(f"\n--- {r['check']} (last output) ---\n{r['tail']}")
    print(f"\n{len(results) - len(failed)}/{len(results)} checks held" + (f"; {len(skipped)} skipped (--fast)" if skipped else "")
          + ("; REGRESSION in: " + ", ".join(r["check"] for r in failed) if failed else "") + ".")
    write_results()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
