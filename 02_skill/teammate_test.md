# Teammate test: add a third client from the docs alone

**Date:** 2026-10-15. **Method:** a fresh subagent (no prior context) was given a read-only allow-list of docs (`02_skill/README.md`, `CONFIG_REFERENCE.md`, `sample_outputs/WALKTHROUGH.md`, `authoring_kit/`, `clients/README.md`, `SKILL.md`, the abc and xyz configs) and forbidden from reading `src/`, `scripts/` and the eval code. Task: add synthetic client **lmn** (different labels, 13 months) and an isolation test, logging every confusion. It did not edit docs or commit; I fixed the docs afterwards.

## Result

| Measure | Result |
|---|---|
| lmn runs cleanly | **Yes**, first attempt: `python scripts/run_pipeline.py lmn 2026-08 --outputs-root <temp>` exit 0, stages Intake / Calculate / Grade commentary, 1 warning (the `Insurance` category it declared has no accounts: "reported as not available, not zero") |
| Data | `LMN Traders`, sheet `Statement of Profit`, header `Particulars`, month format `%B %Y`, sections `Sales` / `Direct Costs` / `Overheads`, fiscal year starts July, Aug 2025 to Aug 2026 (13 months) |
| TTM present | revenue TTM 11,208,531.35; net income TTM 1,992,516.77 (from `summary.json`, Aug 2026) |
| Isolation test | `tests/test_lmn_isolation.py`, 4 tests pass: lmn cannot read or write abc/xyz folders, abc cannot touch lmn |
| Time taken | Agent wall clock: 22:36:17 to 22:37:07 UTC, **about 50 seconds** (15 tool calls). That is the model's speed, not a human's. The agent's own estimate of human effort is 20-30 minutes, mostly item 1 below; **that estimate is unmeasured** |
| Rules respected | The agent reports it read no source code and no secrets. Two things it looked at beyond the allow-list: the first 3 columns of `clients/xyz/xyz_financials.xlsx` (a data file) and a grep of the markdown files for three keywords |

## Confusion log and fixes

| # | Where | Confusion | Cost (agent's estimate) | Fix made |
|---|---|---|---|---|
| 1 | `CONFIG_REFERENCE.md` | **Workbook layout was never specified**: header row position, label column, text vs date month headers, blank section header rows, where totals sit. The agent opened the xyz data file and copied its shape | ~5 min (human: more) | New section "Workbook shape the config describes" with a grid, the rules and the template pointer |
| 2 | `clients/xyz/config.yaml` | Comment points at a generator the task forbade; docs never say it is meant as a template | small | README and CONFIG_REFERENCE now say both generators are copyable templates |
| 3 | add-a-client steps | **Cached values**: totals written as formulas by `openpyxl` have none, and intake stops. Documented only in `03_evals` | 0 (agent wrote numbers) but a real trap | Added to the shape section, with the intake message to expect |
| 4 | `02_skill/README.md` | Step 3 said `src/run_client.py <id>`; the proof line used `scripts/run_pipeline.py xyz 2026-05`. `--outputs-root` / `--clients-root` were in no user doc | ~1 min | Step 3 now uses `run_pipeline.py`; run table documents both flags |
| 5a | `clients/README.md` | Three lines, no steps | small | Rewritten with the 3 steps and the isolation test to copy |
| 5b | `CONFIG_REFERENCE.md` | Does not say what the month argument means, or that TTM needs 12 consecutive months ending there | inferred | Stated in the shape section and README run table |
| 5c | `CONFIG_REFERENCE.md` | Whether category names are free text / reusable | assumed, correct | Stated |
| 5d | `02_skill/README.md` | Says the pipeline writes "flux, packet, manifest", but the console prints only three stage names | cosmetic | Not changed; the files are written (the agent confirmed). Left as is |

Docs that worked (agent's words, abridged): the `CONFIG_REFERENCE.md` field table is why the config worked first time; the minimal-config pointer to xyz and the `test_client_isolation.py` pointer were clear.

## Limits of this test

One run by one model. Models read faster and fill gaps better than a new hire, so the confusion list is a floor, not a ceiling, and the elapsed time says nothing about a human. `/monthly-analysis lmn` (the model-written commentary step) was **not** run. The data is synthetic and tidy; a real export would hit more intake errors (see `config_break_lab_results.json` for what each does).

## Kept in the repo

`clients/lmn/` (config, generator, workbook) and `tests/test_lmn_isolation.py`. Both run in `scripts/regress.py`.
