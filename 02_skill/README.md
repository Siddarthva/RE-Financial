# 02_skill: the monthly financial analysis skill

**Answers:** the brief's "build a skill that produces a monthly financial analysis" requirement.

## What the skill does

Turns a client's monthly workbook into a reviewed analysis. Python computes every number: MoM, margins, TTM, OPEX categories, one-offs, cash runway, gross-margin-drop flags. Claude writes numbered commentary from the computed packet only. A read-only `finance-reviewer` subagent and a deterministic grader check that text. The result is an Excel sign-off pack with the sign-off cells left blank for a human.

## Skill anatomy

| Piece | File | Role |
|---|---|---|
| Skill | [`.claude/skills/monthly-financial-analysis/SKILL.md`](../.claude/skills/monthly-financial-analysis/SKILL.md) | Procedure. Sections: Objective, Inputs and boundaries, Running per client, Engine, then numbered steps 1 Workbook audit, 2 Revenue trend, 3 Profitability and margins, 4 Operating expenses, 5 MoM rules, 6 TTM, 7 Cash and runway, 8 Variance and anomaly flags, 9 Executive commentary, then Export and evaluation, Security, Related skills |
| Engine | [`src/`](../src/): `abc_workbook_adapter.py`, `financial_analysis.py`, `monthly_review.py`, `run_client.py`, `close_artifacts.py` | Parses the workbook, runs the intake gate, computes every figure, writes the review packet and Excel pack |
| Config | [`clients/<id>/config.yaml`](../clients/) | Per-client facts: workbook path, sheet and label names, month format, section totals, account → category map, fiscal-year start, thresholds |
| Agent | [`.claude/agents/finance-reviewer.md`](../.claude/agents/finance-reviewer.md) | Read-only reviewer (tools: Read, Grep, Glob). Reads only the packet and the commentary and returns `approve` or a numbered changes list |
| Command | [`.claude/commands/monthly-analysis.md`](../.claude/commands/monthly-analysis.md) | `/monthly-analysis <client> <YYYY-MM>`: prepare → draft → review → revise once → build pack → report |
| Related skills | [`.claude/skills/skill-catalog.md`](../.claude/skills/skill-catalog.md) | Close review, tie-out, variance and other skills |

The skill, command and agent live under `.claude/` at the repo root because that is where Claude Code discovers them. This folder holds the explanation and sample outputs.

## Why numbers come from code and words from the model

A model asked to do arithmetic can be fluent and wrong. Here the model never sees the workbook, only the packet JSON for one client and month, and may state only numbers in it. Three independent checks then run on the text:

1. [`grade_commentary.py`](../03_evals/grade_commentary.py) matches every number in the commentary to the engine JSON, requires the 3 largest movements to be named, and requires the cash balance and runway.
2. `finance-reviewer` checks causes, direction words and unsupported claims, which code cannot judge. It can be wrong, so:
3. A human signs off. The pack is APPROVED only if the reviewer said `approve` **and** the grader passed. Details: [`03_evals/GRADING.md`](../03_evals/GRADING.md).

## How to run it

| Way | Command | Gives you |
|---|---|---|
| In Claude Code (full flow) | `/monthly-analysis abc 2026-06` | Commentary, reviewer verdict, `outputs/abc/monthly_review_2026-06.xlsx` |
| Pipeline, no model | `python scripts/run_pipeline.py abc 2026-06` | Intake gate, calculation, flux, packet, manifest in `outputs/abc/`. The month is the reporting month; TTM needs 12 consecutive months ending there. Optional `--clients-root DIR` and `--outputs-root DIR` point at other folders (tests and experiments use them so `outputs/` is untouched) |
| QuickBooks sandbox | `python scripts/run_pipeline.py qbo_sandbox 2026-09` | Same stages on live QuickBooks sandbox data (Intuit sample company, not ABC) read by [`src/qbo_adapter.py`](../src/qbo_adapter.py) from the redacted capture in `01_connection/evidence/quickbooks/2026-10-22/` |
| Engine only | `python src/run_client.py abc` | `analysis.xlsx`, `summary.json`, `commentary.md` |

Then approve with `python scripts/approve.py abc 2026-06 --reviewer NAME --reason TEXT`. To run all six close stages in order and stop at the first failed gate, use `/close-review abc 2026-06` ([`.claude/commands/close-review.md`](../.claude/commands/close-review.md)); it applies the `month-end-close-review` workflow and never approves.

## Add a client in 3 steps

Every field is explained, with what breaks if it is wrong, in [`CONFIG_REFERENCE.md`](CONFIG_REFERENCE.md). Worked examples: `xyz` and `lmn` (13 months, July fiscal year, `Particulars` / `Statement of Profit`); `xyz`, a synthetic client whose layout differs from ABC. Its config differs in sheet name (`P&L`), header label (`Line Item`), month format (`%b-%y`, oldest first), section names (`Revenue`, `Cost of Sales`, `Expenses`), total names (`Net Profit`) and fiscal year (April start). No engine code changed.

1. **Config.** Copy [`clients/xyz/config.yaml`](../clients/xyz/config.yaml) to `clients/<id>/config.yaml`. Set the workbook path, sheet names, header label, month format, section and total labels, account → category map and `fiscal_year.start_month`.
2. **Workbook.** Put the client's workbook where the config says. Never edit a source workbook. Its shape must match the grid in [`CONFIG_REFERENCE.md`](CONFIG_REFERENCE.md#workbook-shape-the-config-describes); `clients/xyz/generate_dataset.py` and `clients/lmn/generate_dataset.py` are copyable templates.
3. **Run.** `python scripts/run_pipeline.py <id> <YYYY-MM>` (the intake gate names any label it cannot find, with the sheet and rows searched), then `/monthly-analysis <id> <YYYY-MM>`. Read `warnings` in `outputs/<id>/summary.json` first: unmapped accounts, missing categories and rollup mismatches are reported there, and a missing category is "not available", never zero.

Proof: `python scripts/run_pipeline.py xyz 2026-05` exits 0 (14 months, 1 warning: no Sales & Marketing accounts), and [`tests/test_client_isolation.py`](../tests/test_client_isolation.py) checks that a run cannot read another client's folder. Limit: the parser expects a wide sheet with one column per month. A different layout needs code.

## Extend it: worked example, the G18 gross-margin-drop flag

Request: "flag gross-margin drops over 5 pp". Commit `315a473` changed six files (73 insertions, 3 deletions):

| Step | File | Change |
|---|---|---|
| 1. Threshold in config | `clients/abc/config.yaml` | `thresholds.gross_margin_drop_pp: 5` |
| 2. Engine function | `src/abc_workbook_adapter.py` | `margin_drop_flags(monthly, threshold_pp)` |
| 3. Put it in the packet | `src/monthly_review.py` | reads the threshold from config; adds `gross_margin_drop_threshold_pp` and `gross_margin_flags` |
| 4. Golden case first | `03_evals/golden_cases.json`, `run_golden_evals.py` | G18, expected values hand-computed from rows 14 and 26: Mar 2025, Aug 2025, Apr 2026 |
| 5. Unit test | `tests/test_monthly_review.py` | `test_gross_margin_drop_flags` |

Recipe for a **new metric**: compute it in `src/`, expose it in the packet, add a golden case with a hand-derived value, add a unit test, then run the [regression sequence](../03_evals/README.md#before-any-commit). For a **new flag**: add the threshold to config, a pure function that returns the flagged months, a packet field, and a golden case that pins exactly which months flag. If the packet gains a field, regenerate the committed packet (`run_pipeline.py`): the original change left a stale `review_packet_2026-06.json` that the Phase 1 re-run caught ([`evals_caught.md`](../03_evals/evals_caught.md)).

## Sample outputs, sheet by sheet

[`sample_outputs/`](sample_outputs/) holds abc, 2026-06: copies of files in `outputs/abc/`, including the owner memo [`owner_memo_2026-06.md`](sample_outputs/owner_memo_2026-06.md), written by `/monthly-analysis` step 5.

| File | Contents |
|---|---|
| [`monthly_review_2026-06.xlsx`](sample_outputs/monthly_review_2026-06.xlsx) | Sheets below |
| [`commentary_2026-06.md`](sample_outputs/commentary_2026-06.md) | Reviewed, numbered commentary |
| [`flux_2026-06.json`](sample_outputs/flux_2026-06.json) | Month-over-month flux, largest movements |

| Sheet | What it shows |
|---|---|
| Summary | Client, month, verdict (APPROVED), reviewer verdict, automatic number check (27/27 match) |
| Commentary Sign-off | Each statement, its automatic check, the reviewer's status and note, and a blank sign-off column |
| Numbers Check | Every number as written, its unit, whether it matches the JSON, and the matched fact |
| Top Movements | Events & Conferences +17,970.67; Bad Debts −14,741.53; Usage Fees −11,142.74; each marked as named in the commentary |
| Reviewer Changes | The reviewer's numbered changes (none for this month) |
| Open Questions | Questions for the human, from the reviewer and the automatic cash check (runway 3.4 months at the 3-month average burn) |

The engine run also writes `outputs/abc/analysis.xlsx` (Monthly Trends, Expense Categories, Expense Accounts, Account Values, One-off Items, Data Quality, Commentary).

## Known limits

- **Layout:** one wide sheet with a column per month. Other exports fail intake or need code.
- **Account mapping** is a first pass that a reviewer must approve. Unmapped accounts are reported, not guessed.
- **Causes:** the model may not invent them. Whether the reviewer catches every unsupported claim is not code-checked.
- **Live run:** the saved skill output was graded as saved; the skill was not re-run live on 2026-10-14 ([`verification_matrix.md`](../04_architecture/verification_matrix.md)).
- **QuickBooks:** the analysis can now run on live QuickBooks sandbox data (Intuit sample company, client `qbo_sandbox`); ABC still comes from the workbook. The sandbox has 5 active months, so TTM and YoY are not available there.
- **Engine caveat:** `financial_analysis.category_summary` `expense_mom_pct` has no zero-denominator guard and can return `inf`; treat as undefined.
