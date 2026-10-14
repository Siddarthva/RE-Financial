---
name: monthly-financial-analysis
description: Use when the user asks to analyze, audit, or report on a monthly financial-statement workbook (e.g. the ABC Inc workbook) — including workbook inventory/mapping checks, revenue trends, gross/operating/net margins, operating expense categories, month-over-month changes, trailing-twelve-month (TTM) totals, cash-flow availability, variance/anomaly flags, or executive commentary on those results.
---

# Monthly Financial Analysis

**Quick start**
- **What it does:** turns a client's monthly P&L workbook into revenue, margin, MoM, TTM, expense-category and cash analysis plus review-ready commentary. Python computes every number.
- **Run:** `python src/run_client.py <client>` (e.g. `abc`). Output goes to `outputs/<client>/`. Read `summary.json` → `warnings` first.
- **New client:** copy `clients/abc/config.yaml` to `clients/<new>/config.yaml` and edit the workbook path, sheet and label names, account mapping and fiscal-year start. No code changes.

## Objective
Produce a consistent, review-ready monthly trend analysis for a human finance reviewer. This skill defines workflow and interpretation rules; deterministic Python code is the source of truth for every number. Run only the sections the request needs; a full monthly review runs them all in order.

## Inputs and boundaries
- The source workbook is read-only input. Write all derived files to `outputs/<client>/`; never overwrite or modify the source.
- Work on one client at a time. Never read another client's `clients/<other>/` folder or `outputs/<other>/` (the runner enforces this).
- The ABC Inc workbook (`ABC Inc - Financial Statements.xlsx`) is fictional assessment data. Never present it as RE Financial Services' own accounts.
- Identify entity, period range, currency/units, actual/budget/forecast status, and expense sign convention. If not explicit, mark "not stated in workbook"; do not guess.
- Preserve original account labels and record the source-label → canonical-metric mapping.
- Treat output as decision support for a human reviewer, not audited accounting advice.

## Running per client (no code changes)
- Each client has `clients/<client>/config.yaml`: workbook path, sheet name, header label, month format, section and total row labels, subtotal rows, OPEX account → category mapping, and fiscal-year start month.
- Run: `python src/run_client.py <client>` (e.g. `abc`, `xyz`). Outputs are `outputs/<client>/analysis.xlsx`, `summary.json` and `commentary.md`.
- The run is sandboxed (`src/client_sandbox.py`). Reads are limited to the client's own folder plus shared files outside `clients/` and `outputs/`, and writes are limited to `outputs/<client>/`. Any other access raises `PermissionError`.
- New client: add a folder with a config and data. If the layout differs beyond what the config can express, stop and report it instead of changing engine code for one client.
- Read `summary.json` → `warnings` first. Unmapped accounts, mapped accounts missing from the workbook, declared categories with no data, and rollup mismatches are all reported there. A missing category means "not available", never zero.

## Engine (source of truth for arithmetic)
- `src/abc_workbook_adapter.py`: `parse_wide_income_statement(path, layout)`, `build_monthly_summary(account_month, totals)` (MoM, margins, calendar-checked TTM), `build_expense_category_trends(account_month, subtotal_rows)` (detail OPEX rows only), `build_category_rollup`, `add_fiscal_year` (fiscal-year labels and FYTD), `find_one_off_items`, `generate_commentary`. The defaults reproduce the ABC layout.
- `src/financial_analysis.py`: `normalize_monthly` (validates one row per month; MoM, margins, calendar-checked TTM), `category_summary`, `make_commentary`.
- Golden cases in `03_evals/golden_cases.json` (run `python evals\run_golden_evals.py`) cover the engine rules (G01–G08, G14) and the real ABC workbook (G09–G13). See `03_evals/GRADING.md`.
- Known engine caveat: `financial_analysis.category_summary` `expense_mom_pct` has no zero-denominator guard; treat infinite values as undefined.

## 1. Workbook audit (always first)
1. Inventory sheets and note which statements are present or absent. The ABC Inc workbook has only `Income Statement` and `Balance Sheet` — no cash-flow statement.
2. Locate headers, month formats, and period bounds; check months are unique and consecutive.
3. Classify rows as detail, subtotal, or total to prevent double-counting.
4. Flag blanks, text in numeric cells, `#DIV/0!`, formulas without cached values, and inconsistent signs. Do not silently repair source data.
5. Output: workbook metadata, available-vs-missing statements, account classification, data-quality warnings, and which sections below can safely run.

## 2. Revenue trend
- Monthly revenue schedule with MoM $ and %; min/max months, average, and latest movement.
- Confirm revenue is total recognized income (ABC Inc: `Total Income`), not gross profit or cash collections.
- Report revenue mix only if itemized streams exist; otherwise state that the breakdown is not available. Never invent streams, cohorts, or regions.

## 3. Profitability and margins
- Gross, operating, and net profit and margins, each `profit / revenue`; undefined when revenue is zero.
- Express margin movement in **percentage points** (40% → 42% is +2.0 pp, not +2%).
- Compare gross → operating → net margin to show where conversion drops; no operational hypotheses.

## 4. Operating expenses
- Analyze detail accounts only; list excluded subtotal rows (e.g. `Total Operating Expenses`, `S & M Payroll`, `Total S & M Payroll`, `Marketing`, `Total Marketing`) as an exclusion audit.
- Per category: amount, MoM $ and %, share of total OPEX. Rank top 5 by latest spend and by largest MoM $ change; note new or zeroed accounts.
- Never combine parent subtotals with child lines.

## 5. Month-over-month rules
- Compare adjacent calendar months only; label any gap instead of calling it MoM.
- `% change = (Mₜ − Mₜ₋₁) / |Mₜ₋₁|` only when `Mₜ₋₁ ≠ 0`; otherwise report **undefined (N/A)** — never infinity.
- First month in a series has no MoM. If a profit metric flips sign, report the $ change and state that % change is not meaningful.

## 6. Trailing twelve months (TTM)
- Requires 12 **consecutive calendar months**; 12 rows with a missing month do not qualify. Under 12 months → state that TTM is not available.
- TTM margins use TTM numerators over TTM revenue (e.g. TTM gross margin = TTM gross profit / TTM revenue).
- Label each window by its ending month. Never annualize a shorter period as "TTM"; any run-rate must be labelled as such.

## 7. Cash and runway
- **Cash balance and runway are computed** from Balance Sheet cash (ABC Inc: `Total Cash and Cash Equivalents`) by `cash_position()` in the engine. Burn = average monthly decline in month-end cash over a window; runway = latest cash / burn. Primary window is **3 months** (golden case G17: Jun 2026 cash 713,481.26, 3-month burn 209,656.62, runway 3.4 months). 1- and 6-month windows use the same method; always name the window used.
- Always state the latest cash balance and the runway figure (with the word "runway") in the commentary, and say it is based on past balances only, not a forecast. If cash did not decline over the window, say runway is not calculable.
- Cash-flow statement metrics (CFO / CFI / CFF) are still unavailable: the ABC workbook has no Statement of Cash Flows. Say so as a limitation, but do not let it suppress the Balance Sheet cash and runway figures.
- When a cash-flow statement exists: verify CFO + CFI + CFF = net change in cash, and beginning cash + net change = ending cash tied to balance-sheet cash.
- Never equate net income with operating cash flow, invent add-backs or working-capital changes, or compute runway from net income.

## 8. Variance and anomaly flags
- State the screening method used (default: |MoM %| ≥ 25% with a stated $ floor, one-month spikes that reverse, sign reversals, divergences such as revenue up while gross profit down).
- Rank by absolute $ then %. Frame each item as a neutral review question citing account, period, and figures.
- Never label items as fraud, error, or mismanagement; the reviewer determines root cause.

## 9. Executive commentary
- Header: entity, period range, scope, source file.
- 3–4 bullet summary of validated figures; revenue, margin (pp), and OPEX movements; cash balance and runway (section 7); data limitations (no cash-flow statement, TTM availability, undefined %); at most 3–5 questions for management.
- Name the top 3 line-item movements of the latest month by absolute MoM $ change, ranked across all detail rows (revenue streams, COGS lines, and OPEX categories), not just expenses.
- Grading: `python 03_evals/grade_commentary.py --run-skill` checks every number against the engine and checks the top-3 movements and that cash plus runway are stated (see `03_evals/GRADING.md`).
- Every number must trace to an engine output and name its month/window. Never restate figures differently from the engine.
- No causal language ("because", "driven by", "due to") without explicit source evidence.

## Export and evaluation
- Write a new workbook to `/outputs` with source metadata, mapping/assumptions, monthly metrics, category trends, data-quality warnings, and commentary.
- Run unit tests and golden evals; report the score and any failures. A successful export is not proof of correct mapping.
- Flag ambiguous mappings, units, unusual signs, and potential double-counting for reviewer approval.

## Security
- Never print, commit, or include OAuth credentials, tokens, authorization codes, or `.env` contents.
- QuickBooks MCP use is read-only; never call create/update/delete tools.
- Keep each client's sources, outputs, caches, logs, and credentials isolated.

## Related skills
- `financial-statement-tie-out` — balance-sheet equation and cross-statement checks.
- `fpa-budget-variance` — actuals vs supplied budget/forecast.
- `month-end-close-review`, `fractional-cfo-insights`, `sec-reporting-support`, `company-context` — firm workflows; see `.claude/skills/skill-catalog.md`.

## Version
1.0 — 2026-10-14

## Changelog
- 1.0 (2026-10-14): Baseline. Added Version and Changelog sections; no behaviour change.
