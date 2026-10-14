# 03_evals — evaluations

**Answers:** the brief's evaluation requirement — show the numbers and commentary are right, and that the checks themselves can fail.

**What's here**
- `golden_cases.json` + `run_golden_evals.py` — 17 golden cases (engine rules, and the real ABC workbook with expected values derived by hand from source cells).
- `grade_commentary.py` — every number in a commentary must match the engine JSON; top-3 movements named; cash and runway covered.
- `mutation_test.py` — injects 13 known bugs into a throwaway copy; every one must be caught.
- `GRADING.md` — how each grader scores. `evals_caught.md` — real bugs the evals found. `FINAL_RUN.md` — dated run records.

**Run:** `python 03_evals/run_golden_evals.py`, `python 03_evals/mutation_test.py`, `python 03_evals/grade_commentary.py`; unit tests with `python -m unittest discover -s tests`.
**Rule:** never change an expected value just to make a case pass (see `CLAUDE.md`).
