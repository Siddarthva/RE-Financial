# Brief traceability

Maps each part of the exercise to where it is answered and how to check it. The brief itself is not stored in this repo; the requirement column paraphrases it from the repo's folder structure, so check it against the original wording.

| Requirement (paraphrased) | Answered in | How to check |
|---|---|---|
| Connect Claude to QuickBooks via MCP, safely and read-only | `01_connection/` | `python 01_connection/qbo_test_connection.py abc` (status, no network); evidence in `01_connection/evidence/quickbooks/`; `tests/test_evidence_redaction.py` |
| A skill that produces a monthly financial analysis from the workbook | `02_skill/`, `.claude/skills/monthly-financial-analysis/` | `/monthly-analysis abc 2026-06`; samples in `02_skill/sample_outputs/` |
| Numbers computed by code, not by the model | `src/` | `python -m unittest discover -s tests` |
| Add more clients without code changes | `clients/`, `02_skill/README.md` | `python src/run_client.py xyz`; `tests/test_client_isolation.py` |
| Evaluate correctness, and show the evals can fail | `03_evals/` | `run_golden_evals.py` (17/17), `mutation_test.py` (13/13 caught), `grade_commentary.py` |
| Architecture: hosting, ten-client isolation, credentials, failure points | `04_architecture/architecture.md` | Read the Implemented / Proposed labels; isolation tests above |
| Source workbook untouched | `data/`, `CLAUDE.md` | SHA-256 recorded in `03_evals/FINAL_RUN.md`; compare before and after a run |
| No secrets in the submission | `scripts/scan_secrets.py`, `.claude/hooks/` | `python scripts/scan_secrets.py .`; `python scripts/package_submission.py` scans first |
| Optional: reviewer-facing UI | `05_review_workspace/` | `streamlit run 05_review_workspace/app/Home.py`; `tests/test_ui_numbers.py` |
