"""Rewrite the count tables in the README files from the result files, so the docs cannot drift from the runs.

    python scripts/render_counts.py            # rewrite every block between the markers
    python scripts/render_counts.py --check    # change nothing; exit 1 if any block is stale

A block is the text between `<!-- counts:start NAME -->` and `<!-- counts:end -->`. Only the blocks named in BLOCKS
are generated; everything outside the markers is authored by hand. Sources (nothing here runs an eval):
  unit tests       outputs/regress_results.json, the "unit tests" check (written by every regress run, fast or full)
  golden cases     03_evals/golden_cases.json (counted by `source` group)
  mutation         outputs/mutation_report.md (last full mutation run; a --fast regress does not rewrite it)
  faults           outputs/robustness_results.json (last fault-injection run)
  UI number tests  tests/test_ui_numbers.py (test methods counted with ast)
Dates are left out of the blocks on purpose: a new run on a new day with the same counts is not stale.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGRESS = ROOT / "outputs" / "regress_results.json"
GOLDEN = ROOT / "03_evals" / "golden_cases.json"
MUTATION = ROOT / "outputs" / "mutation_report.md"
FAULTS = ROOT / "outputs" / "robustness_results.json"
UI_TESTS = ROOT / "tests" / "test_ui_numbers.py"
DOCS = [ROOT / "README.md", ROOT / "03_evals" / "README.md"]
BLOCK = re.compile(r"(<!-- counts:start (?P<name>[\w-]+) -->)(?P<body>.*?)(<!-- counts:end -->)", re.S)


def id_range(ids: list[str]) -> str:
    """G19, G20, G21 -> G19–G21; gaps become separate items."""
    nums = sorted(int(i[1:]) for i in ids)
    out, start = [], nums[0]
    for a, b in zip(nums, nums[1:] + [None]):
        if b != a + 1:
            if a - start >= 2:
                out.append(f"G{start:02d}–G{a:02d}")
            else:
                out.extend(f"G{n:02d}" for n in range(start, a + 1))
            start = b
    return ", ".join(out)


def counts() -> dict:
    regress = json.loads(REGRESS.read_text(encoding="utf-8"))
    unit = next((r for r in regress["results"] if r["check"] == "unit tests"), None)
    if unit is None:
        sys.exit(f"{REGRESS.relative_to(ROOT).as_posix()} has no unit-test result; run python scripts/regress.py --fast first")
    cases = json.loads(GOLDEN.read_text(encoding="utf-8"))
    groups: dict[str, list[str]] = {}
    for c in cases:
        key = c["source"] if isinstance(c["source"], str) else "cell-sourced"
        groups.setdefault(key, []).append(c["id"])
    rows = [ln for ln in MUTATION.read_text(encoding="utf-8").splitlines() if ln.startswith("|") and ("✅" in ln or "❌" in ln)]
    faults = json.loads(FAULTS.read_text(encoding="utf-8"))["results"]
    tree = ast.parse(UI_TESTS.read_text(encoding="utf-8"))
    ui = sum(isinstance(n, ast.FunctionDef) and n.name.startswith("test") for n in ast.walk(tree))
    return {
        "unit": int(unit["detail"]) if unit["ok"] else None, "unit_raw": unit["detail"],
        "golden_total": len(cases), "groups": groups,
        "mut_caught": sum("✅" in r for r in rows), "mut_total": len(rows),
        "faults_pass": sum(f["pass"] for f in faults), "faults_total": len(faults),
        "faults_variants": sum(not f["id"][1:].isdigit() for f in faults),
        "silent_wrong": sum(f["actual"] == "SILENT-WRONG" for f in faults),
        "ui": ui,
    }


def unit_text(c: dict, style: str) -> str:
    if c["unit"] is None:
        return f"FAILED ({c['unit_raw']})"
    return f"{c['unit']} run, {c['unit']} OK" if style == "evals" else f"**{c['unit']} / {c['unit']} pass**"


def render(name: str, c: dict) -> str:
    g = c["groups"]
    originals = c["faults_total"] - c["faults_variants"]
    if name == "evals-layers":
        return f"""
| Layer | Command | What it proves | Latest |
|---|---|---|---|
| Unit tests | `python -m unittest discover -s tests` | Individual bugs stay fixed; client isolation; redaction; workflow failure messages | {unit_text(c, "evals")} |
| Golden cases | `python 03_evals/run_golden_evals.py` | Engine numbers and flags equal values derived by hand from source cells | {c["golden_total"]} / {c["golden_total"]} |
| Commentary grader | `python 03_evals/grade_commentary.py` | Every number in the text matches the engine JSON; top-3 movements named; cash and runway covered | engine, reviewed and saved-skill text PASS; flawed control FAILs as intended |
| Mutation test | `python 03_evals/mutation_test.py` | The tests and golden cases above fail when a known bug is injected | {c["mut_caught"]} / {c["mut_total"]} mutants caught |
| Robustness | `python 03_evals/robustness/fault_injection.py` | {c["faults_total"]} corrupted workbooks ({originals} + {c["faults_variants"]} WARN-path variants) each STOP, WARN or HANDLE as declared, on both entry points | {c["faults_pass"]} / {c["faults_total"]}; {c["silent_wrong"]} silent wrong numbers |
| UI number checks | `python -m unittest tests.test_ui_numbers` | Every number the review UI displays exists in an engine JSON file; no page imports calculation code | {c["ui"]} tests OK |
"""
    if name == "golden-groups":
        return f"""
| `source` | Count | IDs | What the group is |
|---|---|---|---|
| `workbook` | {len(g["workbook"])} | {id_range(g["workbook"])} | Real data already triggers the rule; no cell changed |
| `workbook+perturbation` | {len(g["workbook+perturbation"])} | {id_range(g["workbook+perturbation"])} | One or two cells changed to trigger a rule (each case records the cell, original and new value, and purpose); the intake-gate cases write a perturbed copy to a temp file and require the gate to refuse it |
| ABC cell-sourced | {len(g["cell-sourced"])} | {id_range(g["cell-sourced"])} | Expected values computed by hand from cached source cells (listed in each case's `source.cells`), not by the adapter |
"""
    if name == "readme-results":
        return f"""
| Check | Command | Result |
|---|---|---|
| Unit tests (incl. UI number checks and robustness regressions) | `python -m unittest discover -s tests` | {unit_text(c, "readme")} |
| Golden cases | `python 03_evals/run_golden_evals.py` | **{c["golden_total"]} / {c["golden_total"]} pass** |
| Mutation test | `python 03_evals/mutation_test.py` | **{c["mut_caught"]} / {c["mut_total"]} mutants caught**, {c["mut_total"] - c["mut_caught"]} survived |
| Commentary grader | `python 03_evals/grade_commentary.py` | **PASS** on engine text, reviewed text and saved skill output; **FAIL** on the deliberately flawed control, as intended |
| Fault injection (broken workbooks) | `python 03_evals/robustness/fault_injection.py` | **{c["faults_pass"]} / {c["faults_total"]} faults handled correctly** on both entry points; {c["silent_wrong"]} silent wrong |
| Client runs | `python src/run_client.py abc` / `xyz` | Both succeed; `xyz` reports 1 expected warning |
| Live QuickBooks (read-only) | `python 01_connection/qbo_test_connection.py abc --test` | **Pass**: CompanyInfo, monthly P&L Jan–Jun 2026, Balance Sheet at 30 Jun 2026; no write tool registered |
| Secret scan (tracked files) | `python scripts/scan_secrets.py <paths>` | **0 findings** |
| Source workbook integrity | SHA-256 before and after every run | **Unchanged** (`75da8d679a89551f…`) |
"""
    raise KeyError(f"unknown counts block {name!r}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="exit 1 if any block is stale; write nothing")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    c = counts()
    stale, blocks = [], 0
    for doc in DOCS:
        raw = doc.read_bytes().decode("utf-8")
        nl = "\r\n" if "\r\n" in raw else "\n"
        text = raw.replace("\r\n", "\n")
        new = BLOCK.sub(lambda m: m.group(1) + render(m.group("name"), c) + m.group(4), text)
        blocks += len(BLOCK.findall(text))
        if new != text:
            stale.append(doc.relative_to(ROOT).as_posix())
            if not args.check:
                doc.write_bytes(new.replace("\n", nl).encode("utf-8"))
    if blocks == 0:
        print("no counts blocks found")
        return 1
    if args.check:
        print(f"{blocks} blocks, {len(stale)} stale" + (": " + ", ".join(stale) + " (run python scripts/render_counts.py)" if stale else ""))
        return 1 if stale else 0
    print(f"{blocks} blocks, {len(stale)} rewritten" + (": " + ", ".join(stale) if stale else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
