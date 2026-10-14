# Monthly workflow

Who does what for one client and one month. **Code** = deterministic Python. **Model** = Claude. **Human** = reviewer.

| Step | Who | Command / file | Output |
|---|---|---|---|
| 1. Intake checks | Code | `python scripts/run_pipeline.py <client> <YYYY-MM>` | `outputs/<client>/intake_<month>.json` |
| 2. Compute | Code | `src/run_client.py`, `src/abc_workbook_adapter.py` (sandboxed to the client's folders) | `analysis.xlsx`, `summary.json`, `tables_<month>.json`, `flux_<month>.json` |
| 3. Review packet | Code | `python src/monthly_review.py prepare <client> <month>` | `review_packet_<month>.json` (the only data the model sees) |
| 4. Commentary | Model | `/monthly-analysis` with the `monthly-financial-analysis` skill | `commentary_<month>.md`, numbered statements |
| 5. Independent review | Model (read-only subagent) | `.claude/agents/finance-reviewer.md` | `review_<month>.json` |
| 6. Grade | Code | `03_evals/grade_commentary.py` | pass/fail on numbers, top-3 movements, cash risk |
| 7. Sign-off pack | Code | `python src/monthly_review.py build ...` | `monthly_review_<month>.xlsx`: APPROVED only if reviewer and grader both pass |
| 8. Human decision | Human | `python scripts/approve.py <client> <month> --reviewer ... --reason ...` | approval file and `audit_log.jsonl`; the period is then locked |
| 9. View (optional) | Code | `05_review_workspace/` | read-only display of the files above |

Each run writes a manifest (`manifest_<run>-<client>-<month>.json`) with input and output hashes. Re-running an approved period is refused.

Rules throughout: the source workbook is never written; the model never receives the workbook, credentials or another client's files; QuickBooks stays read-only.
