---
name: fpa-budget-variance
description: Use when asked to compare actuals against a supplied budget, forecast, prior month, or prior year — FP&A variance tables, favourable/unfavourable labels, and top variance drivers. Do not use when no comparison data is supplied.
---

# FP&A Budget and Variance Analysis

## Goal
Generate a management-ready variance analysis that explains what changed, quantifies the change, and identifies questions for review.

## Required inputs
Actuals by period and account/category. Budget, forecast, prior-year, or prior-month comparison data is optional but must be clearly identified. Confirm currency and whether expenses are stored as positive values or credits.

## Calculations
- Absolute variance = actual − comparison value
- Variance percentage = (actual − comparison value) / abs(comparison value), only when denominator is non-zero
- For revenue and profit, positive variance is generally favourable; for expenses, negative variance is generally favourable. Confirm client-specific conventions before applying labels.
- Aggregate only comparable periods, entities, currencies, and account mappings.

## Workflow
1. Validate period and category alignment.
2. Match accounts using explicit mappings; flag unmatched accounts rather than silently dropping them.
3. Calculate variance by account/category and in total.
4. Rank the largest absolute contributors.
5. Distinguish observed facts from possible explanations.
6. Draft questions for management; do not attribute causes without evidence.

## Output
- Executive summary
- Actual vs budget/forecast/prior period table
- Favourable/unfavourable conventions used
- Top drivers by absolute impact
- Missing-data and mapping caveats
- Questions and recommended follow-up analysis

## Guardrails
Do not fabricate a budget or forecast. Do not describe a variance as “on plan” without a supplied target. Avoid causal claims based only on correlation or a single period.

## Version
1.0 — 2026-10-14

## Changelog
- 1.0 (2026-10-14): Baseline. Added Version and Changelog sections; no behaviour change.
