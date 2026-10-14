---
name: month-end-close-review
description: Use when asked to run or review a month-end close — close checklist status, reconciliations from a trial balance or GL export, exception log, and reviewer sign-off pack. Read-only; never posts entries.
---

# Month-End Close Review

## Goal
Produce a structured close-status pack for a human accountant. This is a workflow aid, not an autonomous close or journal-entry posting agent.

## Required inputs
- Client/entity and close month
- Trial balance or general ledger export
- Relevant bank, AR, AP, payroll, revenue, and balance-sheet support where available
- Prior-period balances and close checklist, if supplied

## Workflow
1. Confirm entity, period, currency, accounting basis, and source files.
2. Inventory files and identify missing or duplicate inputs.
3. Check period coverage, account identifiers, opening/closing balances, and debit/credit conventions.
4. Reconcile only where both sides of the reconciliation are present; show formula, source, and difference.
5. Flag unreconciled balances, stale items, unexpected movements, missing support, and cutoff questions.
6. Separate arithmetic/data-quality exceptions from accounting judgments.
7. Produce a close checklist with status: `complete`, `review`, `blocked`, or `not_applicable`.
8. Provide a reviewer sign-off section and list unresolved items.

## Output
- Scope and files reviewed
- Checklist table with owner if provided, status, evidence, and unresolved issue
- Reconciliation summary with calculated differences
- Exceptions ordered by potential materiality, without claiming materiality unless thresholds are provided
- Questions for the accountant
- Reviewer sign-off: name/date fields left blank

## Guardrails
- Never create, post, update, or delete accounting records unless a separately approved workflow explicitly allows it. Default to read-only.
- Do not invent reconciliations or mark an item complete without supporting evidence.
- Do not call a difference an error until timing, mapping, and source completeness have been considered.
