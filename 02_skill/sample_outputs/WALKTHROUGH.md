# Walkthrough: the sample outputs, requirement by requirement

All files in this folder are copies of `outputs/abc/` for **ABC Inc, June 2026**, produced by `python scripts/run_pipeline.py abc 2026-06` and `/monthly-analysis abc 2026-06` (copied 2026-10-15). Python computed every number; the commentary was drafted by Claude from the review packet and checked by a grader, a reviewer agent and (pending) a human.

## Where each brief requirement lives

| Brief asks for | Where to look | Example figure (Jun 2026) |
|---|---|---|
| Revenue | `analysis.xlsx` → Monthly Trends, column `revenue`; commentary §Headline and §Revenue | 195,898.16; −12,452.80 (−5.98%) vs May |
| Margins | Monthly Trends: `gross_margin_pct`, `operating_margin_pct`, `net_margin_pct`; commentary §Margins | Gross margin 70.15%, +3.11 pp vs May |
| Opex by category | `analysis.xlsx` → Expense Categories (6 categories × month: amount, MoM, share of opex) and Expense Accounts (detail); commentary §Opex | Payroll & Benefits 331,397.16; Technology 34,089.48 |
| Month-over-month | Monthly Trends `revenue_mom_change`, `revenue_mom_pct`; Expense Categories `mom_change`; `monthly_review` → Top Movements and Flux Items | Largest: Events & Conferences +17,970.67 |
| Trailing twelve months | Monthly Trends `*_ttm` columns (blank until 12 consecutive months exist); commentary §Revenue | TTM revenue 2,303,975.51 |
| Short commentary an owner should know | `commentary_2026-06.md` (7 sections, fixed order); `owner_memo_2026-06.md` (plain-language version) | 18 numbered statements |
| For a human reviewer to finish | `monthly_review_2026-06.xlsx` → Commentary Sign-off (blank sign-off column), Open Questions (Answer column), Cover ("Awaiting human approval") | 0 sign-offs by design |

## `monthly_review_2026-06.xlsx` (the sign-off pack)

| Sheet | What it is | How to use it |
|---|---|---|
| Cover | One-page dashboard: client, month, verdict, sign-off status, revenue (and vs same month last year), gross margin, net income (and excluding one-offs), cash, runway, data checks passed (18/18), flux items flagged, numbers matched (46/46), sections check, reviewer checklist, owner-memo grade | Check the verdict line first. `APPROVED` here means *the automatic checks passed and the reviewer agent said approve*; it does **not** mean a human signed. The sign-off status line says nobody has |
| Summary | Reviewer verdict and the automatic number check (every number matched) | One-glance health of the draft |
| Commentary Sign-off | One row per commentary statement: text, automatic number check, reviewer status and note, result, blank human column | Read each statement; the human initials the sign-off column |
| Numbers Check | Every number found in the commentary, its unit, whether it matches the engine JSON, and the matched fact | Audit trail for "where did this figure come from" |
| Top Movements | The 3 largest line-item changes vs the prior month and whether the commentary named each | Missing a large movement is a grader failure |
| Data checks | The intake gate's checks: sheet present, header row, contiguous months, total rows, gross profit = revenue − COGS, operating income = gross profit − opex, sections foot to their lines, Balance Sheet balances. Each has a cell reference and a fix hint | If any is FAIL the pack is not produced |
| Flux Items | Lines that moved by at least the materiality rule (min dollars AND min %, or a sign flip) with severity | Candidates for explanations; the rule is shown, from the client's config |
| Reviewer Changes | Numbered changes the reviewer agent asked for ("None" for this month) | Empty is a good outcome, not proof |
| Open Questions | Questions for the client or owner, with why it matters, owner and a blank Answer | The human closes these before sign-off |

## `analysis.xlsx` (the engine's full tables)

| Sheet | Contents |
|---|---|
| Monthly Trends | One row per month: revenue, COGS, gross profit, opex, operating income, net income, MoM, margins, TTM columns, fiscal year and FYTD |
| Expense Categories | Opex rolled up to the client's reporting categories, with MoM and share of opex |
| Expense Accounts | Every detail opex account by month (subtotals excluded so nothing is double-counted) |
| Account Values | The parsed source grid, so a reviewer can compare to the workbook |
| One-off Items | Accounts flagged as one-offs, by month |
| Data Quality | Warnings (unmapped accounts, missing categories, month gaps, outliers). "None" when clean. A missing category is "not available", never zero |
| Commentary | The engine's own mechanical commentary (not the reviewed, sectioned text) |

## The commentary

`commentary_2026-06.md` has a title and seven `##` sections in fixed order: Headline, Revenue, Margins, Opex, Cash & runway, One-offs, Questions. Statements are numbered continuously so a reviewer can say "change 7". Rules it follows: every number comes from the packet and names its month or window; no cause is stated, only questions; cash runway is labelled "past balances only, not a forecast"; an empty section says so in one line.

## Companion files

| File | Purpose |
|---|---|
| `flux_2026-06.json` | Flux table with the materiality rule and each flagged line's source cell |
| `flux_explanations_2026-06.md` | Preparer notes per flagged line: evidence only plus one question each; never a cause |
| `client_questions_2026-06.md` | The open questions as a client request list |
| `owner_memo_2026-06.md` | Plain-language owner summary built from the same packet |

## What this sample cannot show

One month of one client. The reviewer agent's judgement varies between runs (`03_evals/live_consistency_2026-10-15.md`). Whether a human accepts the commentary is not tested. QuickBooks data is not an input.
