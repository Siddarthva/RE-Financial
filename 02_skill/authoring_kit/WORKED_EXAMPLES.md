# Worked examples: the checklist applied to the Phase B skills

Each row shows how one skill or command went through the 8 steps in `CHECKLIST.md`. Use these as models for the next skill.

## `financial-statement-tie-out` (intake stage), v2.0

| Step | What was done |
|---|---|
| 1 Capture | "The Balance Sheet balances every month, Current Year Earnings equals YTD net income, subtotals foot, GP = revenue − COGS. If not, tell me the cell and how to fix it." |
| 2 Numbers vs words | All four checks are engine code in `src/` (intake gate writes `intake_<month>.json`). The skill only explains failed checks. |
| 3 SKILL.md | Rebuilt from `SKILL_TEMPLATE.md`; output is a `Check \| Result \| Cell \| Plain-language explanation \| Fix` table. |
| 4 Golden | G19–G25. G23 unbalanced Balance Sheet (Mar 2026), G24 Current Year Earnings ≠ YTD net income (Sep 2025), G25 missing row label. Each perturbs a copy of the ABC workbook; the source stays read-only. |
| 5 Triggers | `03_evals/skill_triggers/financial-statement-tie-out.json`; the negative is a budget-variance request. |
| 6 Evals | Unit (`tests/test_intake_balance_sheet.py`), golden, trigger. |

## `flux-explanations` (preparer stage), v1.0

| Step | What was done |
|---|---|
| 1 Capture | "For each flagged flux item, write the evidence (amount, prior, change, source cell, related movements) and one question for the client. Never a cause." |
| 2 Numbers vs words | Flux items, changes, percentages and source cells come from `flux_<month>.json`. The skill copies them and never derives new ones. |
| 3 SKILL.md | The "Never do" section lists the banned causal words, which the grader also enforces. |
| 4 Golden | G26–G28 are flux rows read by hand from source cells (Events & Conferences C65, Bad Debts C31, Sales Commission C23). G29: the saved output passes its grader. |
| 5 Triggers | 3 positive and 1 negative ("write the executive commentary" → `monthly-financial-analysis`). |
| 6 Evals | `03_evals/grade_workflow_skills.py flux`: numbers match the JSON, no causal words, exactly one `?` per item, every item appears once. Negative tests are in `tests/test_grade_workflow_skills.py`. |

## `client-questions` (package stage), v1.0

| Step | What was done |
|---|---|
| 1 Capture | "Turn the open questions and flagged items into a PBC list: item, why it matters, document needed, priority." |
| 2 Numbers vs words | Sources are `flux:<account>`, `reviewer:<n>` and `auto:cash`. Priority is a fixed rule (High if \|change\| ≥ 10,000 or the cash flag is set; otherwise Medium), not a judgement. |
| 3 SKILL.md | Rows from the same source are merged so no request appears twice; every row lists all its sources. |
| 4 Golden | G26–G28 (the flagged items the requests trace to); G30: the saved output passes its grader. |
| 5 Triggers | 3 positive and 1 negative ("fill in the flux explanation column" → `flux-explanations`). |
| 6 Evals | `grade_workflow_skills.py questions`: every row traces to a source, every source is covered, no duplicates, priorities follow the rule, numbers match. |

## `/close-review <client> <YYYY-MM>` (command, all stages)

| Step | What was done |
|---|---|
| 1 Capture | "Run intake → calculate/flux → draft → reviewer → package → wait for human approval, and stop at the first failed gate." |
| 2 Numbers vs words | Gate status is read from files on disk by `scripts/close_review_status.py`, never decided by the model. |
| 3 Command file | `.claude/commands/close-review.md`. The tools it may run are listed in `allowed-tools`. Stage 6 never approves; the person runs `scripts/approve.py`. |
| 4 Tests | `tests/test_close_review_status.py` covers the stage table and stopping at the first failed gate. |
| 5 Triggers | `03_evals/skill_triggers/close-review.json`. |
| 6 Evals | Status script on ABC 2026-06: stages 1–5 PASS, stage 6 WAITING. |

Steps 7 (accountant sign-off) and 8 (publish) are recorded in `.claude/skills/skill-catalog.md` and `03_evals/FINAL_RUN.md`.
