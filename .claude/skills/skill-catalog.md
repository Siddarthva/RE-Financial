# Skill Catalog

All project skills live under `.claude/skills/<skill-name>/SKILL.md`. Claude Code discovers them when it is started from the repo root. Each skill's `description` states when it should trigger. The Python analysis engine (`src/`) remains the source of truth for arithmetic.

## Skills

Status rule (see `02_skill/authoring_kit/`): **Validated** needs a SKILL.md from the template, 3+ golden cases on real ABC data, and 3+ positive and 1+ negative trigger cases in `03_evals/skill_triggers/`, all passing. Otherwise **Draft**. `03_evals/skill_triggers/` does not exist yet, so no skill is Validated.

| Skill | Workflow stage | Status | Version | Evals | Trigger cases |
|---|---|---|---|---|---|
| `monthly-financial-analysis` | Calculate / draft | Draft | 1.1 | Golden 33 (G01-G33), commentary + section grader, memo grader, mutation (see FINAL_RUN), fault injection 26/32 (see FINAL_RUN) | 0 |
| `financial-statement-tie-out` | Intake | Draft | 1.0 | None skill-specific (engine checks covered by unit tests) | 0 |
| `month-end-close-review` | Reviewer / package | Draft | 1.0 | None | 0 |
| `fpa-budget-variance` | Calculate / flux | Draft | 1.0 | None | 0 |
| `fractional-cfo-insights` | Package (owner brief) | Draft | 1.0 | None | 0 |
| `sec-reporting-support` | Out of close workflow (SEC support) | Draft | 1.0 | None | 0 |
| `company-context` | Routing (before intake) | Draft | 1.0 | None | 0 |

Paths: `.claude/skills/<skill>/SKILL.md`. Command `/monthly-analysis` (`.claude/commands/monthly-analysis.md`) is not a skill file and has no version section; it is covered by `03_evals/live_consistency_2026-10-15.md`.

## Sections inside `monthly-financial-analysis`
Earlier separate analytics skills are now numbered sections of `monthly-financial-analysis`:
1. Workbook audit
2. Revenue trend
3. Profitability and margins
4. Operating expenses
5. Month-over-month rules
6. Trailing twelve months (TTM)
7. Cash flow (availability check)
8. Variance and anomaly flags
9. Executive commentary

## Selection and execution rules
- Run section 1 (workbook audit) before interpreting an unfamiliar workbook or when mapping correctness is in doubt.
- Run sections only when their required inputs exist. Do not derive cash-flow figures from income-statement data; `ABC Inc - Financial Statements.xlsx` has no cash-flow statement.
- Keep source workbooks read-only and write generated outputs to `/outputs`.
- These workflows reflect the supplied assessment brief's description of a finance-and-accounting firm serving entrepreneurs (month-end close, FP&A, fractional CFO, SEC reporting). They do not assert lending, underwriting, payment-processing, or other unverified services.
