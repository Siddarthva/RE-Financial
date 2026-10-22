# CLAUDE.md — standing rules for this project

These rules apply to every task in this repo. They override convenience.

## Secrets
- Never read, print, or commit `.env` files, API tokens, refresh/access tokens, or OAuth authorization codes.
- If a task seems to need a secret, stop and ask instead of opening the file.

## Source workbook is read-only
- Never modify the original workbook (`data/ABC Inc - Financial Statements.xlsx`).
- Write all generated files to `/outputs` (project-root `outputs/`), never alongside or over the source.

## Evals
- Never change expected values in evals (e.g. `03_evals/`) just to make them pass.
- If an expected value looks wrong, show the source-cell evidence (sheet, cell, value/formula) and ask me before changing anything.

##Token rules: don't print full files or raw data; show diffs and summary tables only. Read only the files named in the task. Don't re-run passing tests unless code changed. End every task with: Changed / Verified / Unverified (max 5 lines each).
## QuickBooks MCP is read-only
- Keep `QUICKBOOKS_DISABLE_WRITE`, `QUICKBOOKS_DISABLE_UPDATE`, and `QUICKBOOKS_DISABLE_DELETE` set to `true`.
- Do not flip these flags, bypass them, or call create/update/delete tools.

## End-of-task report
At the end of every task, report:
1. **What changed** — files created/edited and why.
2. **What was verified** — checks actually run and their results.
3. **What is still unverified** — anything assumed, skipped, or not tested.

## UI rule
- `app/` never calculates financial figures: the UI shows only files inside the selected runs/runN folder; project pages are labelled.

## Runs
- `runs/` is permanent. Never delete `runs/` or any `runs/runN` folder (not in tests, cleanup or "to start fresh"); a run never writes to `outputs/` or touches another run. Tests use temp folders only.
