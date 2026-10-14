---
name: financial-statement-tie-out
description: Use when asked to tie out, reconcile, or sanity-check financial statements or trial balances — balance-sheet equation (assets = liabilities + equity), net income to equity roll-forward, totals vs components, and cross-statement consistency.
---

# Financial Statement Tie-Out

## Goal
Identify arithmetic inconsistencies and reconciliation questions before human review.

## Checks
- Assets = liabilities + equity, when the statement structure and period definitions permit
- Net income agrees with the income statement and retained-earnings/equity roll-forward, allowing for distributions, contributions, and other disclosed adjustments
- Cash flow ending cash agrees to balance-sheet cash when both reports share the same entity, currency, and cutoff
- Opening balance + period movement = closing balance where roll-forward data exists
- Totals equal displayed components within an explicitly stated rounding tolerance
- Periods, currencies, accounting basis, signs, and entity IDs are consistent

## Workflow
1. Capture report names, periods, dates, currencies, and accounting bases.
2. Normalize signs and account labels only with explicit, documented rules.
3. Compute checks using deterministic code or transparent arithmetic.
4. Return pass/fail/not-testable with the calculation and source references.
5. Investigate mismatches as questions; do not silently “fix” source values.

## Output
A table with check, formula, expected value, observed value, difference, status, and source references, followed by a prioritized exception list.

## Guardrails
A balance-sheet equation balancing does not prove the statements are correct. Do not treat a Balance Sheet as a period activity report; it is normally a point-in-time statement. Compare it to a specific as-of date or explicitly explain a report's date-column semantics.
