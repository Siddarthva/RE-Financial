---
description: Run all six close stages for a client and month in order (intake, calculate and flux, draft, reviewer, package, human approval) and stop at the first failed gate with a stage table
argument-hint: <client> <YYYY-MM>   (example: abc 2026-06)
allowed-tools: Bash(python scripts/run_pipeline.py *), Bash(python scripts/close_review_status.py *), Bash(python src/monthly_review.py *), Bash(python 03_evals/grade_workflow_skills.py *), Bash(python 03_evals/grade_commentary.py *), Read, Write, Edit, Agent
---

Run the close review for **$ARGUMENTS** (client id, then month as YYYY-MM). Work from the repo root. If either argument is missing, stop and ask.

After every stage run `python scripts/close_review_status.py <client> <month>`. It prints the stage table from the files on disk. If the stage you just ran is not PASS, **stop**: show the table, name the failed gate and its note, and do nothing further.

1. **Intake.** Run `python scripts/run_pipeline.py <client> <month>`. It runs the intake gate (including the Balance Sheet checks) and writes `intake_<month>.json`. If it refuses the workbook, apply the `financial-statement-tie-out` skill to explain each failed check with its cell and fix, then stop.
2. **Calculate + flux.** Same run writes the review packet and `flux_<month>.json`; if the packet is missing run `python src/monthly_review.py prepare <client> <month>`. Stop if it fails.
3. **Draft.** Follow the `/monthly-analysis` step 2: write `outputs/<client>/commentary_<month>.md` from the packet only. Then use the `flux-explanations` skill to write `flux_explanations_<month>.md` and run its grader (`python 03_evals/grade_workflow_skills.py flux <client> <month>`). The commentary must use the fixed section order (see `/monthly-analysis` step 2); the Draft gate fails without every section. Revise at most twice.
4. **Reviewer.** Spawn the `finance-reviewer` subagent with the packet and commentary paths and nothing else. Save its JSON unchanged as `review_<month>.json`. Verdict `changes`: fix only what it lists, once, and re-run it. Still not `approve`: stop.
5. **Package.** Use the `client-questions` skill to write `client_questions_<month>.md` and run its grader. Then run `python src/monthly_review.py build <client> <month> --commentary outputs/<client>/commentary_<month>.md --review outputs/<client>/review_<month>.json`.
6. **Human approval.** Do not approve. Run the status script; stage 6 reads WAITING. `approve.py` also refuses while an Open Questions row has a blank Status. Tell the person to run `python scripts/approve.py <client> <month> --reviewer "<name>" --reason "<why>"` themselves.

Finish with the stage table and: Changed / Verified / Unverified (max 5 lines each).

Rules: the source workbook is read-only; write only under `outputs/<client>/`; never open `.env`, token or credential files; touch no other client's folder; no causes unless the packet states them.
