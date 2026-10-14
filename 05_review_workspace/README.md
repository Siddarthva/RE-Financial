# 05_review_workspace — optional review UI

**Answers:** nothing the brief requires. It is an optional extra for a reviewer.

A Streamlit app (`app/`) showing runs, flux, evidence, approvals, evaluations and architecture.

**Run:** `pip install streamlit`, then from the repo root `streamlit run 05_review_workspace/app/Home.py`. Generate data first with `python scripts/run_pipeline.py abc 2026-06`.

**Display only.** `app/` never calculates a financial figure. It reads JSON in `outputs/` (engine outputs, manifests, eval results, audit log). Its buttons run the existing scripts and read the result back. `tests/test_ui_numbers.py` checks that every displayed number exists in the engine JSON and that no page imports calculation code.
