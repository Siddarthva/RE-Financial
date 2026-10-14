"""Run the existing golden-case script and write outputs/eval_results.json for the workspace.

    python scripts/export_eval_results.py [--no-run]

No evaluation logic lives here. It runs evals/run_golden_evals.py unchanged and parses its printed
PASS/FAIL lines; it joins them to evals/golden_cases.json for input / expected / grading text (read only).
Mutation results are parsed from outputs/mutation_report.md and unit-test counts from evals/FINAL_RUN.md
(the slow scripts are not re-run here). --no-run re-parses the last golden output in outputs/golden_run.txt.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT.parent / "outputs"
LINE = re.compile(r"^(PASS|FAIL) (G\d+) \S+ (.*?): (.*)$")


def source_kind(src) -> str:
    if isinstance(src, str) and "perturb" in src:
        return "perturbed"
    if isinstance(src, str) and "synth" in src:
        return "synthetic"
    return "workbook"


def run_golden(no_run: bool) -> tuple[str, bool]:
    log = OUT / "golden_run.txt"
    if no_run:
        return log.read_text(encoding="utf-8", errors="replace"), True
    r = subprocess.run([sys.executable, "evals/run_golden_evals.py"], cwd=PROJECT, capture_output=True, text=True,
                       encoding="utf-8", timeout=300, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    text = r.stdout + r.stderr
    log.write_text(text, encoding="utf-8")
    return text, r.returncode == 0


def golden(text: str) -> dict:
    cases = {c["id"]: c for c in json.loads((PROJECT / "evals" / "golden_cases.json").read_text(encoding="utf-8"))}
    rows = []
    for ln in text.splitlines():
        m = LINE.match(ln.strip())
        if not m:
            continue
        status, cid, name, actual = m.groups()
        c = cases.get(cid, {})
        rows.append({"id": cid, "name": c.get("name", name), "source": source_kind(c.get("source")),
                     "passed": status == "PASS", "input": c.get("input"), "expected": c.get("expected"),
                     "actual": actual, "tolerance": c.get("grading"), "perturbation": (c.get("perturbation") or {}).get("purpose")})
    return {"cases": rows, "total": len(rows), "passed": sum(r["passed"] for r in rows)}


def mutation() -> dict | None:
    p = OUT / "mutation_report.md"
    if not p.is_file():
        return None
    rows = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if ln.startswith("|") and len(cells) == 4 and cells[0] not in ("Mutation", "---"):
            by = [] if cells[3] in ("—", "") else [t.strip() for t in cells[3].split(",")]
            rows.append({"mutation": cells[0], "module": cells[1].strip("`"), "caught": cells[2].startswith("✅"), "caught_by": by})
    return {"rows": rows, "total": len(rows), "caught": sum(r["caught"] for r in rows), "source": "outputs/mutation_report.md"}


def unit() -> dict | None:
    p = PROJECT / "evals" / "FINAL_RUN.md"
    m = re.search(r"\|\s*Unit tests\s*\|[^|]*\|\s*(\d+) run, (\d+) OK", p.read_text(encoding="utf-8")) if p.is_file() else None
    return {"total": int(m.group(1)), "passed": int(m.group(2)), "source": "ai_solutions_builder_free/evals/FINAL_RUN.md"} if m else None


def main() -> int:
    text, ok = run_golden("--no-run" in sys.argv)
    result = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "golden": golden(text),
              "mutation": mutation(), "unit": unit()}
    (OUT / "eval_results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    g = result["golden"]
    print(f"golden {g['passed']}/{g['total']}")
    return 0 if ok and g["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
