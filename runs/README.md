# runs/

One folder per analysis run: `run1`, `run2`, ... The next number is the highest existing + 1 and is never reused. This folder is permanent: never delete it or any `runN` inside it. A run never writes to `outputs/` and never changes another run. The `runN` folders are git-ignored; this README is tracked so the folder is always visible.

Create a run:

- `python scripts/new_run.py <client> <YYYY-MM>`: pipeline only (no Claude).
- `/demo-run <client> <YYYY-MM>` in Claude Code, or the UI button "Run full analysis with Claude": full run. Add `--with-regress` to also save `regress.py --fast`.

```
runs/runN/
  SUMMARY.md            run number, date/time (IST), client, month, git branch/commit, workbook hash, grade, verdicts, evals, headline numbers, final commentary, open questions
  run.json              machine-readable version, status (running | complete | failed), start/end/duration of every stage
  01_intake/            intake_<month>.json
  02_numbers/           review_packet_<month>.json, flux_<month>.json, analysis.xlsx, tables, manifest, audit log
  03_commentary/        commentary_<month>_draft.md, commentary_<month>_final.md, commentary_grade_<month>.json, commentary_final_grade_<month>.json
  04_review/            review_<month>_first.json, review_<month>_final.json
  05_evals/             golden_results.txt, commentary_grade_report.txt, flawed_control_check.txt, workbook_hash.txt, evals_summary.json, (regress_fast.json)
  06_pack/              monthly_review_<month>.xlsx, owner_memo_<month>.md
  logs/                 pipeline.log, claude_session.log (UI button)
```

A pipeline-only run has `NOT_RUN.md` in `03_commentary/`, `04_review/` and `06_pack/`. A failed run keeps its folder with status `failed`, the error in `run.json` and the log in `logs/`. `_work/` exists only while a full run is in progress; `finish` moves its files into the layout above.
