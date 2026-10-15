---
name: flux-explanations
description: Use when a flux table exists for a client month and the preparer must draft the "Preparer explanation" for each flagged item — evidence only (amount, prior, change, source cell, related movements) plus one question for the client. Never states a cause. Do not use to write executive commentary (monthly-financial-analysis) or the client request list (client-questions).
---

# Flux Explanations (preparer stage)

## When to trigger
- Positive: "draft the preparer explanations for the June flux", "fill in the explanation column for the flagged items", "write the flux notes for ABC 2026-06".
- Negative: "write the executive commentary" → `monthly-financial-analysis`; "make the client request list" → `client-questions`.

## Inputs
- `outputs/<client>/flux_<YYYY-MM>.json` (items, rule, source cells). Produced by `python scripts/run_pipeline.py <client> <YYYY-MM>`.
- If it is missing or has no items, stop and say so. Do not invent items.

## Procedure
1. Read `items` from the flux JSON. One output line per item, in the file's order (largest change first).
2. Each line, as `N. **Account** (source cell, section): …`, contains, in this order:
   - the current amount against the prior amount, the dollar change with its sign, and the percent change (percent omitted if the JSON has none); say "the sign changed" for SIGN_FLIP;
   - `Related movements in the same section:` the other flagged items in that section with their dollar changes; add `Related movement in <other section>:` for flagged items elsewhere; write "none flagged" if there are none;
   - `Question for the client:` **exactly one** question.
3. Write `outputs/<client>/flux_explanations_<YYYY-MM>.md` with the rule line (thresholds from the JSON `rule`) at the top, then the numbered lines.
4. Run `python 03_evals/grade_workflow_skills.py flux <client> <YYYY-MM>`. Fix wording until it prints PASS. Never edit the flux JSON.

## Never do
- State or hint at a cause. No "because", "due to", "driven by", "caused by", "reflects", "led to", "as a result of".
- Use a number that is not in the flux JSON. Python computed it; copy it, do not round differently or derive new ones.
- Ask two questions in one item, or none.
- Leave out the source cell, or drop a flagged item.

## Output format
Numbered lines, one per flagged item, each with the source cell (for example `Income Statement!C65`) and one `?`.

## Evals
- Golden cases: G26–G28 (flux rows read by hand from source cells), G29 (saved output grades PASS).
- Grader: `03_evals/grade_workflow_skills.py flux` — every number matches the flux JSON, no causal words, one question per item, every item once. Negative tests: `tests/test_grade_workflow_skills.py`.
- Trigger cases: `03_evals/skill_triggers/flux-explanations.json`.

## Version
1.0 — 2026-10-14

## Changelog
- 1.0 (2026-10-14): New skill for the preparer stage of the close workflow.
