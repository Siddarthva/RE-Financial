---
description: Monthly analysis for a client and month, reviewed by finance-reviewer, saved as an Excel sign-off pack in outputs/<client>/
argument-hint: <client> <YYYY-MM>   (example: abc 2026-06)
allowed-tools: Bash(python src/monthly_review.py *), Read, Write, Edit, Agent
---

Run the monthly analysis for **$ARGUMENTS** (client id, then month as YYYY-MM). Work from the repo root. If either argument is missing, stop and ask.

1. **Analyse.** Run `python src/monthly_review.py prepare <client> <month>`. It writes `outputs/<client>/analysis.xlsx` and `outputs/<client>/review_packet_<month>.json`. Stop and report if it fails (unknown client, month without a prior month, workbook problem).
2. **Draft the commentary** following the `monthly-financial-analysis` skill, using only the packet's numbers. Write `outputs/<client>/commentary_<month>.md` in the fixed section order with a `##` heading for each: Headline · Revenue · Margins · Opex · Cash & runway · One-offs · Questions. Under the headings, one statement per line, numbered `1.`, `2.`, `3.` … continuing across sections, no other numbered lines. Include the same-month-last-year comparison (packet `yoy`) and net income excluding one-offs (packet `adjusted_net_income`). Cover revenue, gross profit, operating expenses and net income with MoM and margins; name all three `top_movements`; state TTM only if the packet has it; state the cash balance and runway if the packet has `cash`; mention each data-quality warning and any one-off in the month. Describe what changed, never why. Put no causes, forecasts or recommendations in the statements.
3. **Review.** Spawn the `finance-reviewer` subagent with the two file paths (packet and commentary) and no other context. It must cite a statement number for every change and return the four checklist scores (numbers, coverage, causes, tone). Save its JSON block, unchanged, as `outputs/<client>/review_<month>.json`.
4. **Revise once.** If the verdict is `changes`, fix only what the changes list says, rewrite the whole commentary file with Write (keep the numbering), and run the reviewer again. Never edit the packet or the reviewer's output. Do not loop more than twice; unresolved items go to the pack as they are.
5. **Build the pack.** Run `python src/monthly_review.py build <client> <month> --commentary outputs/<client>/commentary_<month>.md --review outputs/<client>/review_<month>.json`. It writes `outputs/<client>/monthly_review_<month>.xlsx` with a Cover sheet (KPIs, verdict, sign-off status), the Commentary Sign-off sheet (blank sign-off column), the number check, top movements, a Data checks sheet, the flagged Flux Items with the client's materiality threshold, reviewer changes and an Open Questions sheet, plus the one-page `outputs/<client>/owner_memo_<month>.md`. Build refuses to approve a pack whose review lacks statement numbers or scores, whose commentary lacks a section, or whose numbers do not match.
6. **Report** in five lines: verdict, numbers matched, changes outstanding, open-question count, and the workbook path. Do not sign off for anyone; the sign-off cells stay empty. `scripts/approve.py` later refuses approval while any open question has a blank Status.

Note: `outputs/` is at the repo root, so every path here starts with `outputs/`.

Rules: the source workbook is read-only; write only under `outputs/<client>/`; never open `.env`, token or credential files; touch no other client's folder.
