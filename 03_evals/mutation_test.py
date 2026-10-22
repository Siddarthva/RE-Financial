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
CA, MR = "src/close_artifacts.py", "src/monthly_review.py"
QB = "src/qbo_adapter.py"

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
    # --- Added 2026-10-15: the intake gate, flux, year-over-year and adjusted net income live outside the two engine modules above.
    ("Flux ignores the percentage threshold", CA,
     'elif abs(delta) >= min_d and v.get("mom_pct") is not None and abs(v["mom_pct"]) >= min_p:',
     'elif abs(delta) >= min_d and v.get("mom_pct") is not None:'),
    ("Year-over-year compares with last month", MR,
     "    prior = month - pd.DateOffset(years=1)\n    if prior not in monthly.index:",
     "    prior = month - pd.DateOffset(months=1)\n    if prior not in monthly.index:"),
    ("Adjusted net income sign reversed", MR,
     'effect = sum(o["amount"] if o["section"] == "income" else -o["amount"] for o in items)',
     'effect = sum(-o["amount"] if o["section"] == "income" else o["amount"] for o in items)'),
    ("Balance Sheet tie-out tolerance made huge", CA,
     "BS_TOLERANCE = 0.01",
     "BS_TOLERANCE = 1e12"),
    ("Section footing check made blind", CA,
     'off = [(f"{m:%Y-%m}", d) for m, d in diff.items() if not abs(d) <= 0.01]',
     'off = [(f"{m:%Y-%m}", d) for m, d in diff.items() if not abs(d) <= 1e12]'),
    ("Prior-month column no longer required", CA,
     'for m, role in ((month, "the requested month"), (prior, f"the prior month of {month}")):',
     'for m, role in ((month, "the requested month"),):'),
    # --- Added 2026-10-22: the QuickBooks adapter and the long-format parser.
    ("QuickBooks: parent account's own postings ignored", QB,
     "if isinstance(head_cols, list) and any(",
     "if False and isinstance(head_cols, list) and any("),
    ("QuickBooks: section total kept inside its section (double count)", QB,
     "emit(s_label, s_vals, None if depth == 0 else section)",
     "emit(s_label, s_vals, group_section if depth == 0 else section)"),
    ("QuickBooks: empty cell read as missing instead of zero", QB,
     "        return 0.0, None  # QuickBooks leaves",
     "        return None, 'blank'  # QuickBooks leaves"),
    ("Long format: duplicate (account, month) check removed", AD,
     "if (account, month) in seen:",
     "if False:"),
    ("Long format: months shifted by one", AD,
     'month = month.to_period("M").to_timestamp()',
     'month = (month.to_period("M") + 1).to_timestamp()'),
    ("Long format: missing (account, month) read as zero", AD,
     "values[a].get(m, np.nan) for m in months] for a in order]",
     "values[a].get(m, 0.0) for m in months] for a in order]"),
]

def make_copy(dest: Path):
    for name in ("src", "tests", "03_evals", "clients", "01_connection", "scripts", "02_skill", ".claude", "deploy"):  # tests import from 01_connection/, scripts/ and 02_skill/; hook and skill tests read .claude/
        shutil.copytree(ROOT / name, dest / name, ignore=shutil.ignore_patterns("__pycache__", "settings.local.json"))
    # Saved skill outputs (commentary, flux notes, client questions, review) that tests and golden cases G29-G33 read.
    shutil.copytree(ROOT / "outputs" / "abc", dest / "outputs" / "abc", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(ROOT / "Dockerfile", dest / "Dockerfile")  # tests/test_deploy.py reads it
    (dest / "data").mkdir()
    shutil.copy2(ROOT / WORKBOOK, dest / WORKBOOK)  # tests read the copy; the original is never opened for write


def run_evals(project: Path, fail_fast: bool = False):
    """Return (failing unit tests, failing golden case ids). With fail_fast the unit run stops at the first failing test:
    enough to call a mutant caught, and it keeps the whole run to minutes. The baseline always runs in full."""
    unit = subprocess.run([sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-v"] + (["-f"] if fail_fast else []),
                          cwd=project, capture_output=True, text=True, encoding="utf-8", timeout=1800)
    # Inline "test_x (...) ... FAIL" is replaced by the docstring's first line for a test that has one, so also read the
    # "FAIL: test_x (...)" / "ERROR: test_x (...)" summary lines; otherwise a failing documented test looks like no failure.
    failed_tests = sorted(set(re.findall(r"^(test_\w+) \(.*?\) \.\.\. (?:FAIL|ERROR)", unit.stderr, re.M))
                          | set(re.findall(r"^(?:FAIL|ERROR): (test_\w+) \(", unit.stderr, re.M)))
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
            tests, golden = run_evals(work, fail_fast=True)
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
