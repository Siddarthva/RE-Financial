# SETUP: for a reviewer starting from nothing

This folder is a self-contained copy of the AI Solutions Builder prototype. **You do not need any QuickBooks account, API key or secret to run or check it.** Everything below runs offline on the supplied workbook.

## 1. What you need

- Python 3.11 or newer (built and tested on 3.13.5, Windows 11). No other language runtime.
- `pip install -r requirements.txt` (pandas, openpyxl, PyYAML). `pytest` is optional; the commands below use `unittest`.
- Optional: [Claude Code](https://claude.com/claude-code), only for the skills, the `finance-reviewer` agent, the `/monthly-analysis` command and the safety hooks (section 5).

Open a terminal **in this folder**. Generated files go to an `outputs/` folder created **next to this folder** (one level up), never inside it and never over the source workbook.

## 2. Five-minute check

| Step | Command | Expected |
|---|---|---|
| Unit tests | `python -m unittest discover -s tests` | `Ran 90 tests … OK` (the 15 UI tests skip with a message until step 3 of section 2b has produced `outputs/`) (some tests print a journal-entry plan; that is normal) |
| Golden cases | `python evals/run_golden_evals.py` | `Score: 17/17 (100%)` |
| Both clients | `python src/run_client.py abc` then `python src/run_client.py xyz` | abc: 18 months, 0 warnings. xyz: 14 months, 1 warning (no Sales & Marketing accounts) |
| Commentary grader | `python evals/grade_commentary.py --commentary sample_outputs/abc/commentary_2026-06.md` | `RESULT: PASS` (27/27 numbers, 3/3 movements, cash risk covered) |
| Same grader, engine's own text | `python evals/grade_commentary.py` | `RESULT: PASS` (28/28 numbers, 3/3 movements, cash risk covered) |
| Mutation test (about 2–3 min) | `python evals/mutation_test.py` | `13/13 mutants caught; 0 survived` |
| Secret scan | `python scripts/scan_secrets.py .` | `Secret-like findings: 0` |
| Load plan, no network | `python scripts/load_workbook_to_sandbox.py --dry-run` | 18 journal entries printed, nothing written to QuickBooks |

`evals/FINAL_RUN.md` records the author's run of these commands, with timestamps and counts, **including three earlier attempts that failed in part** and why. Your numbers should match its final run.

## 2b. Workspace UI (optional, offline)

Read-only review workspace over the engine's JSON. It never calculates a figure and never reads credentials.

```
pip install -r requirements.txt
python scripts/run_pipeline.py abc 2026-06     # writes ../outputs/abc/ (intake, flux, tables, packet, manifest)
python scripts/run_pipeline.py xyz 2026-05
streamlit run app/Home.py
```

Overview, Financial Analysis, Insights & Review (approve/reject calls `scripts/approve.py`), Data Sources, Runs, Evaluations, Architecture & Security. Pages show an empty state until their engine files exist: the commentary, reviewer and Excel pack come from `/monthly-analysis` (section 5). `python -m unittest tests.test_ui_numbers` checks every displayed number against the JSON.

## 3. Where things are

| Path | What |
|---|---|
| `src/` | Engine and runners. `abc_workbook_adapter.py` parses and computes; `run_client.py` runs a client from its config; `client_sandbox.py` isolates clients; `monthly_review.py` builds review packets and the Excel sign-off pack |
| `clients/abc/config.yaml`, `clients/xyz/` | Per-client config (no secrets). `xyz` is a synthetic 14-month client with different labels and a missing category, with its generator |
| `ABC Inc - Financial Statements.xlsx` | The supplied source workbook. Read-only; SHA-256 `75da8d679a89551f9e46b3563b7cfc724d9aaeabe0444b0214d455a0b335a0ea` |
| `.claude/skills/` | The 7 skills and `skill-catalog.md` (each description says when it triggers) |
| `.claude/agents/`, `.claude/commands/`, `.claude/hooks/`, `.claude/settings.json` | The reviewer agent, `/monthly-analysis`, the safety hooks and their registration |
| `evals/` | `golden_cases.json` (17 cases with source-cell references), runners, commentary grader, mutation test, **`GRADING.md`** (how scoring works; also copied to the top level), `FINAL_RUN.md` |
| `tests/` | Unit tests |
| `docs/` | `architecture.md` (one page), `connection_decision.md`, `evals_caught.md` (every bug the evals caught), `part1-quickbooks-mcp.md`, `dependency_risk.md` (npm audit of the upstream MCP server) |
| `evidence/quickbooks/` | Redacted QuickBooks sandbox requests and responses, with a README that explains what each proves |
| `config/qbo_write.env.example` | Template for the optional sandbox write script. Placeholders only |
| `app/` | The workspace UI (`Home.py` is the entry point) |
| `scripts/` | `run_pipeline.py`, `approve.py`, `qbo_test_connection.py`, `export_eval_results.py` (used by the UI), `load_workbook_to_sandbox.py` (sandbox journal-entry loader, dry-run by default) and `scan_secrets.py` |
| `sample_outputs/` | Outputs from the author's runs, for comparison. Includes the Excel sign-off pack `abc/monthly_review_2026-06.xlsx` |

## 4. Read these first

1. `docs/architecture.md`, one page, with what is implemented versus proposed and what breaks first.
2. `evals/GRADING.md`, then `evals/FINAL_RUN.md`.
3. `docs/connection_decision.md` for the QuickBooks choice and credential flow.
4. `docs/evals_caught.md` for the defects found by checking engine output against source cells.

## 5. Using it with Claude Code (optional)

Start Claude Code **from this folder** so the project skills, agent, command and hooks load. The hooks are registered in `.claude/settings.json`:

- a PreToolUse hook blocks reads of `.env`, `*token*` and `*credential*` files;
- a PostToolUse hook runs the unit tests after edits to `src/*.py`.

`/monthly-analysis abc 2026-06` runs the analysis, drafts commentary, has the `finance-reviewer` agent check it, and builds `outputs/abc/monthly_review_2026-06.xlsx`. Sign-off cells are left empty for a person. A newly added agent file only loads when Claude Code starts. The command writes under `../outputs/`.

## 6. Optional: QuickBooks

Not needed to check the work. The QuickBooks evidence in `evidence/quickbooks/` was captured from Intuit's **developer sandbox** through the official `quickbooks-online-mcp-server` (read-only, stdio). To reproduce it you would need your own Intuit developer app and sandbox company, then follow `docs/connection_decision.md`. Rules if you do:

- Copy `.mcp.json.example` to `.mcp.json` (env var names only; set values outside this folder).
- Keep credentials in the MCP server's own `.env` or a file outside this folder. Never paste them into this project.
- Keep `QUICKBOOKS_DISABLE_WRITE`, `_UPDATE` and `_DELETE` set to `true` for the MCP server.
- `scripts/load_workbook_to_sandbox.py --apply` is a **separate** write path for sandbox journal entries and needs its own env file (template in `config/`). It has never been run against QuickBooks.

## 7. Known gaps (so they do not surprise you)

- **The saved skill output was graded, not regenerated:** `sample_outputs/skill_commentary.md` passes the grader (36/36 numbers, 3/3 movements, cash covered), but `/monthly-analysis` was not re-run live for the final run.
- QuickBooks sample data is **not** an input to the analysis, which reads the supplied workbooks. The loader and the QBO-vs-workbook comparison are built and tested only against a fake.
- Only two clients exist; ten-client isolation is a design plus a tested file-level guard, not a deployed guarantee.
- The reviewer is an LLM, so repeat runs can differ. The deterministic grader covers numbers, the top 3 movements and cash only.
- Tested on Windows only.
