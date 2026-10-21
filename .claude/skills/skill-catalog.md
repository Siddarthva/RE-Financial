# Skill Catalog

All project skills live under `.claude/skills/<skill-name>/SKILL.md`. Claude Code discovers them when it is started from the repo root. Each skill's `description` states when it should trigger. The Python analysis engine (`src/`) remains the source of truth for arithmetic.

## Skills

Status rule (see `02_skill/authoring_kit/`): **Validated** needs a SKILL.md from the template, 3+ golden cases on real ABC data, and 3+ positive and 1+ negative trigger cases in `03_evals/skill_triggers/`, all passing. Otherwise **Draft**. `03_evals/skill_triggers/` has one file per skill and command (11 files, 4 cases each: 3 positive, 1 negative); the last live routing run passed 44/44 (2026-10-14, `outputs/trigger_eval_results.json`). No skill has yet been promoted through the authoring-kit checklist step 8, so every status below is still Draft.

Nine skills:

| Skill | Workflow stage | Status | Version | Evals | Trigger cases |
|---|---|---|---|---|---|
| `monthly-financial-analysis` | Calculate / draft | Draft | 1.2 | Golden 33 (G01-G33), commentary + section grader, memo grader, mutation 19/19, fault injection 38/38 (see FINAL_RUN) | 4 |
| `financial-statement-tie-out` | Intake | Draft | 2.0 | Golden G19-G25 pin the intake refusals it explains (engine checks; the skill text itself has no grader) | 4 |
| `flux-explanations` | Calculate / flux (preparer notes) | Draft | 1.0 | Golden G26-G28 (the flux rows it explains), G29 (its saved output), output grader (`grade_workflow_skills.py flux`) | 4 |
| `client-questions` | Package (client request list) | Draft | 1.0 | Golden G30, output grader (`grade_workflow_skills.py questions`) | 4 |
| `month-end-close-review` | Reviewer / package | Draft | 1.0 | None | 4 |
| `fpa-budget-variance` | Calculate / flux | Draft | 1.0 | None | 4 |
| `fractional-cfo-insights` | Package (owner brief) | Draft | 1.0 | None | 4 |
| `sec-reporting-support` | Out of close workflow (SEC support) | Draft | 1.0 | None | 4 |
| `company-context` | Routing (before intake) | Draft | 1.0 | None | 4 |

Paths: `.claude/skills/<skill>/SKILL.md`. Commands `/monthly-analysis` (`.claude/commands/monthly-analysis.md`) and `/close-review` (`.claude/commands/close-review.md`) are not skill files and have no version section; each has 4 trigger cases, and `/monthly-analysis` is covered by `03_evals/live_consistency_2026-10-15.md`.

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
