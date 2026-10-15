---
name: financial-statement-tie-out
description: Use when asked to tie out, reconcile, or sanity-check financial statements or a close's intake — the Balance Sheet balances every month, Current Year Earnings equals year-to-date net income, subtotals foot to their lines, and gross profit = revenue − COGS. Also use to explain in plain language why the intake gate refused a workbook. Do not use to compare actuals with a budget or prior period (fpa-budget-variance) or to run the whole close (month-end-close-review).
---

# Financial Statement Tie-Out (intake stage)

## When to trigger
- Positive: "tie out the ABC workbook for June", "does the balance sheet balance every month?", "why did intake refuse the file?", "check that Current Year Earnings agrees to net income".
- Negative: "compare June with the budget" → `fpa-budget-variance`; "run the month-end close" → `month-end-close-review`.

## Inputs
- `outputs/<client>/intake_<YYYY-MM>.json`, written by the engine's intake gate (`close_artifacts.intake_gate`, run by `scripts/run_pipeline.py` and `src/monthly_review.py prepare`).
- If the file is missing, run `python scripts/run_pipeline.py <client> <YYYY-MM>` first. If the run refuses the workbook, use the refusal message instead.

## Procedure
1. Python runs the checks; this skill never recomputes them. The engine tests: the Income Statement has its total rows; every amount is a number; gross profit = revenue − COGS; operating income = gross profit − operating expenses; each section total foots to its lines; and, when the client has a Balance Sheet, **Total Assets = Total Liabilities and Equity every month** and **Current Year Earnings = year-to-date net income** (fiscal year per the client config), each with a 0.01 tolerance.
2. Read `checks` in the intake JSON. For every check write one line: check, PASS/FAIL, cell reference.
3. For each FAIL write three things in plain language: **what is wrong** (the numbers in `detail`), **where** (the cell in `cell_ref`), **the fix** (the "Fix:" hint in `detail`, otherwise "ask the client to re-export").
4. Say whether the close may continue: any FAIL means stop at intake.

## Never do
- Recompute, round, or "correct" a figure. Quote the engine's numbers only.
- Guess why a check failed. Name the cell and the fix; ask the client for the cause.
- Edit the source workbook or any expected eval value.
- Say a balancing Balance Sheet proves the statements are right.

## Output format
A table `Check | Result | Cell | Plain-language explanation | Fix`, then one line: `Intake: PASS — continue` or `Intake: FAIL — stop, n checks failed`.

## Evals
- Golden cases: G19–G25 (intake gate, including G23 unbalanced Balance Sheet, G24 Current Year Earnings mismatch, G25 missing row), `03_evals/run_golden_evals.py`.
- Unit tests: `tests/test_intake_balance_sheet.py`.
- Trigger cases: `03_evals/skill_triggers/financial-statement-tie-out.json`.

## Version
2.0 — 2026-10-14

## Changelog
- 2.0 (2026-10-14): Rebuilt from the authoring-kit template for the intake stage. Added the Balance Sheet checks (balances every month; Current Year Earnings = YTD net income), plain-language failure explanations with cell and fix, golden cases G23–G25 and trigger cases.
- 1.0 (2026-10-14): Baseline. Added Version and Changelog sections; no behaviour change.
