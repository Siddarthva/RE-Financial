---
name: company-context
description: Use when a request involves RE Financial Services' scope or service lines, or before picking an accounting/analytics workflow for a new client task — establishes the verified firm context (month-end close, FP&A, fractional CFO, SEC reporting) and routes to the right skill.
---

# Company Context and Scope

## Source-grounded business context
The supplied Build Exercise brief describes RE Financial Services Private Limited as a **full-service finance and accounting firm for entrepreneurs**, operating across the US and India and building as an AI-native firm. It names these service areas:
- Month-end close
- Financial planning and analysis (FP&A)
- Fractional CFO support
- SEC reporting

Use this description as the project context. Do not invent products, regulated lending activities, credit underwriting, loan origination, consumer lending, payment processing, or financial-advisory offerings unless a trusted source or the user explicitly confirms them.

## Operating principles
1. The team’s accountants provide accounting judgment; the system supplies repeatable workflows, calculations, evidence, and draft commentary.
2. Treat all outputs as drafts for a qualified human reviewer, especially accounting conclusions and SEC-reporting content.
3. Identify the client, entity, reporting period, currency, accounting basis, and source system before analysis.
4. Do not blend data from different clients, entities, or reporting periods.
5. Cite the exact workbook sheet, account, period, or source report behind material findings where possible.
6. If a source does not support a conclusion, state “not available from supplied data.”
7. Never present the fictional ABC Inc assessment workbook as RE Financial Services’ own financial statements.
8. Do not make regulatory, legal, tax, audit-opinion, or investment recommendations.

## Routing
- Close/reconciliation work → `month-end-close-review`
- Budget, forecast, actuals, and management reporting → `fpa-budget-variance`
- Executive planning and cash runway → `fractional-cfo-insights`
- Financial statement consistency checks → `financial-statement-tie-out`
- SEC-related disclosure preparation → `sec-reporting-support`
- Monthly trend analysis (audit, revenue, margins, OPEX, MoM, TTM, cash-flow availability, anomalies, commentary) → `monthly-financial-analysis`
