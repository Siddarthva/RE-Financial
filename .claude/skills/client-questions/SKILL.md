---
name: client-questions
description: Use when the open questions and flagged flux items for a client month must become a client-ready request list (PBC-style) — item, request, why it matters, document needed, priority. Do not use to draft the preparer's flux notes (flux-explanations) or the executive commentary (monthly-financial-analysis).
---

# Client Questions (package stage)

## When to trigger
- Positive: "turn the open questions into a client request list", "what do we need from ABC for June?", "make the PBC list for this close".
- Negative: "fill in the flux explanation column" → `flux-explanations`; "summarise June for the owner" → `fractional-cfo-insights`.

## Inputs
- `outputs/<client>/flux_<YYYY-MM>.json` (flagged items).
- `outputs/<client>/review_<YYYY-MM>.json` (`open_questions`, numbered 1.. in file order = `reviewer:<n>`).
- `outputs/<client>/review_packet_<YYYY-MM>.json` (cash and runway; `auto:cash` applies when runway is under 6 months).
- If a file is missing, stop and say which. Do not write requests from memory.

## Procedure
1. Build the source list: every flagged flux item (`flux:<account>`), every reviewer question (`reviewer:<n>`), and the cash flag (`auto:cash`).
2. Merge sources that point at the same thing into **one row** (a reviewer question about Bad Debts and the Bad Debts flux item are one row, source `flux:Bad Debts; reviewer:1`). One reviewer question may cover several items; list every source.
3. For each row write: **Request** (a question or document ask, neutral wording), **Why it matters** (one sentence, packet numbers only), **Document needed** (a concrete document), **Priority**.
4. Priority follows materiality: **High** if a linked flux item moves by 10,000 or more (absolute) or the source is `auto:cash`; otherwise **Medium**. Do not use Low for flagged items.
5. Write `outputs/<client>/client_questions_<YYYY-MM>.md`: the priority rule line, then a table with columns `# | Item | Source | Request | Why it matters | Document needed | Priority`. Sort High first.
6. Run `python 03_evals/grade_workflow_skills.py questions <client> <YYYY-MM>`; fix until PASS.

## Never do
- Add a question that traces to no flagged item, reviewer note, or cash flag.
- Repeat a request in two rows.
- State or imply a cause. A request may ask whether something is one-off or timing; it must not say why it happened.
- Use a number that is not in the flux, review, or packet files.
- Set priority by feel.

## Output format
Markdown table as above; one row per distinct request.

## Evals
- Golden cases: G26–G28 (the flagged items the requests trace to), G30 (saved output grades PASS).
- Grader: `03_evals/grade_workflow_skills.py questions` — every row traces to a source, every flagged item, reviewer question and the cash flag is covered, no duplicates, priority follows the rule, numbers match. Negative tests: `tests/test_grade_workflow_skills.py`.
- Trigger cases: `03_evals/skill_triggers/client-questions.json`.

## Version
1.0 — 2026-10-14

## Changelog
- 1.0 (2026-10-14): New skill for the package stage of the close workflow.
