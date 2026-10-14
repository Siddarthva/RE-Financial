"""Mutation testing: inject known bugs one at a time and check that the evals catch each one.

Each mutant is applied to a throwaway copy of the project (src/, tests/, 03_evals/, clients/, 01_connection/,
scripts/ and a copy of the workbook); the original files are never modified. For each mutant the unit tests and golden cases
are run and every failing test / case is recorded. A mutant that nothing fails "survives" — that is
an eval gap.

Usage:  python 03_evals/mutation_test.py            (writes outputs/mutation_report.md)
"""
from __future__ import annotations
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = "data/ABC Inc - Financial Statements.xlsx"
REPORT = ROOT / "outputs" / "mutation_report.md"
FA, AD = "src/financial_analysis.py", "src/abc_workbook_adapter.py"

# (mutation, file, original text, mutated text). Each original must occur exactly once.
MUTANTS = [
    ("Reverse month order", FA,
     'out = out.sort_values("month").reset_index(drop=True)',
     'out = out.sort_values("month", ascending=False).reset_index(drop=True)'),
    # The source columns run newest first (C=Jun 2026 … T=Jan 2025); this mutant labels them as if oldest first.
    ("Reverse month order", AD,
     "    if len(date_cols) < 2:\n",
     "    date_cols = list(zip([j for j, _ in date_cols], [m for _, m in date_cols][::-1]))\n    if len(date_cols) < 2:\n"),
    ("Flip revenue sign", FA,
     '    if out["revenue"].isna().any():',
     '    out["revenue"] = -out["revenue"]\n    if out["revenue"].isna().any():'),
    ("Flip revenue sign", AD,
     "            rows[metric] = row\n",
     '            rows[metric] = -row if metric == "revenue" else row\n'),
    # Total S & M Payroll and Total Marketing kept alongside their detail rows, so those lines count twice.
    ("Sum subtotals twice", AD,
     "    exclude = {r.casefold() for r in subtotal_rows} | {",
     "    exclude = set() | {"),
    ("Shift months by one", FA,
     'out["month"] = pd.to_datetime(out["month"], errors="coerce").dt.to_period("M").dt.to_timestamp()',
     'out["month"] = (pd.to_datetime(out["month"], errors="coerce").dt.to_period("M") + 1).dt.to_timestamp()'),
    ("Shift months by one", AD,
     'date_cols.append((j, parsed.to_period("M").to_timestamp()))',
     'date_cols.append((j, (parsed.to_period("M") + 1).to_timestamp()))'),
    ("Drop one opex category", FA,
     "    x = df.copy()\n",
     '    x = df[df["expense_category"] != sorted(df["expense_category"].unique())[-1]].copy()\n'),
    ("Drop one opex category", AD,
     "    expense = account_month.loc[names]\n",
     "    expense = account_month.loc[names[:-1]]\n"),
    ("TTM over 11 months", FA,
     "            rolling = out[col].rolling(12, min_periods=12).sum()",
     "            rolling = out[col].rolling(11, min_periods=11).sum()"),
    ("TTM over 11 months", AD,
     'out[f"{metric}_ttm"] = out[metric].rolling(12, min_periods=12).sum()',
     'out[f"{metric}_ttm"] = out[metric].rolling(11, min_periods=11).sum()'),
    ("Wrong margin denominator (gross profit / COGS)", FA,
     'out["gross_margin_pct"] = (out["gross_profit"] / out["revenue"])',
     'out["gross_margin_pct"] = (out["gross_profit"] / (out["revenue"] - out["gross_profit"]))'),
    ("Wrong margin denominator (gross profit / COGS)", AD,
     'out["gross_margin_pct"] = (out["gross_profit"] / out["revenue"])',
     'out["gross_margin_pct"] = (out["gross_profit"] / out["cost_of_goods_sold"])'),
]


def make_copy(dest: Path):
    for name in ("src", "tests", "03_evals", "clients", "01_connection", "scripts"):  # tests import from 01_connection/ and scripts/
        shutil.copytree(ROOT / name, dest / name, ignore=shutil.ignore_patterns("__pycache__"))
    (dest / "data").mkdir()
    shutil.copy2(ROOT / WORKBOOK, dest / WORKBOOK)  # tests read the copy; the original is never opened for write


def run_evals(project: Path):
    """Return (failing unit tests, failing golden case ids, raw log tail)."""
    unit = subprocess.run([sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-v"],
                          cwd=project, capture_output=True, text=True, encoding="utf-8", timeout=600)
    failed_tests = sorted(set(re.findall(r"^(test_\w+) \(.*?\) \.\.\. (?:FAIL|ERROR)", unit.stderr, re.M)))
    failed_tests += sorted(set(f"{m} (setUpClass)" for m in re.findall(r"^ERROR: setUpClass \(.*?\.(\w+)\)", unit.stderr, re.M)))
    golden = subprocess.run([sys.executable, "-X", "utf8", "03_evals/run_golden_evals.py"],
                            cwd=project, capture_output=True, text=True, encoding="utf-8", timeout=600)
    failed_golden = re.findall(r"^FAIL (G\d+)", golden.stdout, re.M)
    if golden.returncode not in (0, 1):  # runner itself crashed
        failed_golden.append("runner crashed")
    return failed_tests, failed_golden


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="mutation_") as tmp:
        base = Path(tmp) / "baseline"
        make_copy(base)
        tests, golden = run_evals(base)
        if tests or golden:
            print(f"Baseline is not green; fix it first. Failing: {tests + golden}")
            return 2
        rows = []
        for i, (name, rel, old, new) in enumerate(MUTANTS, 1):
            work = Path(tmp) / f"mutant_{i}"
            make_copy(work)
            target = work / rel
            code = target.read_text(encoding="utf-8")
            if code.count(old) != 1:
                raise SystemExit(f"Mutant {i} ({name}, {rel}): expected 1 match, found {code.count(old)}. Update MUTANTS.")
            target.write_text(code.replace(old, new), encoding="utf-8")
            tests, golden = run_evals(work)
            caught_by = golden + tests
            rows.append((name, Path(rel).name, bool(caught_by), caught_by))
            print(f"[{i}/{len(MUTANTS)}] {name} in {Path(rel).name}: {'caught' if caught_by else 'SURVIVED'}")
            shutil.rmtree(work, ignore_errors=True)

    lines = ["| Mutation | Module | Caught? | By which test |", "|---|---|---|---|"]
    for name, module, caught, by in rows:
        lines.append(f"| {name} | `{module}` | {'✅ yes' if caught else '❌ no — gap'} | {', '.join(by) or '—'} |")
    survivors = sum(not c for _, _, c, _ in rows)
    lines.append(f"\n{len(rows) - survivors}/{len(rows)} mutants caught; {survivors} survived.")
    table = "\n".join(lines)
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(f"# Mutation test report\n\n{table}\n", encoding="utf-8")
    print("\n" + table + f"\n\nReport: {REPORT}")
    return 0 if survivors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
