# Checklist: from "an accountant describes a procedure" to "a validated skill"

Times are for one skill with the accountant on hand. Total: about 4 h 25 min.

| # | Step | Output | Time |
|---|---|---|---|
| 1 | **Capture the procedure.** The accountant describes it aloud or in bullets: inputs, order of steps, what "wrong" looks like. Write it down verbatim. | Raw procedure notes | 30 min |
| 2 | **Separate numbers from words.** Mark every step that computes a figure. Those belong in Python (`src/`), not in the skill. The skill only writes about packet values. | Split list: engine steps vs. writing steps | 20 min |
| 3 | **Draft SKILL.md from `SKILL_TEMPLATE.md`.** Fill every section; write the description as "Use when… Do not use when…". | Draft SKILL.md (status: Draft) | 40 min |
| 4 | **Write 3+ golden cases** on real ABC data from `GOLDEN_CASE_TEMPLATE.json`. Compute expected values by hand from cached source cells, never by copying engine output. | Entries in `03_evals/golden_cases.json` | 60 min |
| 5 | **Write trigger cases:** 3+ positive, 1+ negative, in `03_evals/skill_triggers/`. | Trigger case file | 20 min |
| 6 | **Run the evals:** unit tests, golden, commentary grader, trigger evals, secret scan. Fix the skill (never the expected values) until all pass. If an expected value looks wrong, show source-cell evidence and ask the owner. | Passing run log | 45 min |
| 7 | **Accountant review.** The accountant reads one real output and signs off, or lists changes. Repeat step 6 after any change. | Sign-off note | 30 min |
| 8 | **Publish.** Set Version and Changelog, mark status Validated in `.claude/skills/skill-catalog.md`, add a line to `03_evals/FINAL_RUN.md`, commit. | Validated skill | 20 min |

A skill missing any of steps 4, 5 or 6 stays **Draft**.
