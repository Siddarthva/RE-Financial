# Submission Overview

A read-only QuickBooks connection, a monthly financial-analysis skill, an evaluation harness and a one-page architecture note, built for the RE Financial Services build exercise. Python computes every number; Claude writes the commentary; a second, read-only Claude agent and a deterministic grader check it; a human signs off.

## What was built

| Part | What exists and works today |
|---|---|
| **1. Connection** | Intuit's own `quickbooks-online-mcp-server`, run locally over stdio against the Intuit developer **sandbox**, with the write, update and delete flags set to `true` (disabled), so no write tool is registered. Live read-only checks passed on 2026-10-14: CompanyInfo, a monthly P&L (Jan–Jun 2026), a Balance Sheet at 30 Jun 2026 (balances at 5,488.75) and a tool list of 71 read tools with no create, update or delete. |
| **2. Skill** | `/monthly-analysis <client> <YYYY-MM>`: an intake gate, the engine (MoM, TTM, margins, OPEX categories, one-offs, cash runway, gross-margin-drop flags), numbered commentary, a `finance-reviewer` agent, and an Excel sign-off pack with blank sign-off cells. A second client (`xyz`, different layout) runs from a config file with no engine change. |
| **3. Evals** | {{golden}} golden cases derived by hand from source cells, a commentary grader, a mutation test ({{mut}} injected bugs), a {{fault}}-fault robustness suite and {{unit}} unit tests. |
| **4. Architecture** | A one-page note (`04_architecture/architecture.md`), a workflow page for each of seven workflows, and a traceability matrix from every line of the brief to a command or file. |
| **Extra** | A Streamlit review workspace (`05_review_workspace/`) that only displays numbers read from JSON files in `outputs/`, plus approve, reject and lock with an audit log. |

## Deliverables map

| Brief item | Where | PDF in this folder |
|---|---|---|
| Working connection | `01_connection/` | 01_Connection_Architecture |
| Skill files | `.claude/skills/`, `.claude/agents/`, `.claude/commands/`, `02_skill/` | 02_Skill_and_Analysis_Workflow |
| Eval cases and grading | `03_evals/` | 03_Evals_and_Regression |
| One-page architecture note | `04_architecture/architecture.md` | 04_Architecture_OnePage |
| Workflow documentation | `04_architecture/workflows/` | 05_Workflows_Appendix |
| Proof of every brief line | `04_architecture/verification_matrix.md`, `03_evals/robustness/` | 06_Verification_and_Robustness_Report |

## Results (from `03_evals/FINAL_RUN.md`, {{final_run_date}})

| Check | Result |
|---|---|
| Unit tests | {{unit_result}} |
| Golden cases | {{golden_result}} |
| Mutation test | {{mut_result}} |
| Robustness (fault injection) | {{fault_result}} |
| Secret scan of tracked files | {{scan_result}} |
| Source workbook SHA-256 | unchanged (`75da8d679a89551f…`) before and after every run |

A flawed-commentary control is also graded and **fails** as intended (11/12 numbers, 2/3 movements, cash risk missing), which shows the grader can fail.

## What is not done

- **Stretch goal: not done.** The workbook was never loaded into the sandbox. `load_workbook_to_sandbox.py` produces an 18-entry dry-run plan only; a live P&L check found no `Workbook Load` accounts, and `--compare` exits 1.
- **Team hosting is a design, not a build.** Per-client OAuth grants, token stores and server processes are labelled *Proposed*. The server has a stdio transport only.
- **Ten clients are untested.** Two clients exist (`abc`, `xyz`). Isolation is an in-process audit hook plus name-based hooks, not an OS or credential boundary.
- **The skill was not re-run live in the final run.** The saved skill output is graded as it stands on disk.
- **Tone and causes are not code-graded.** The reviewer is an LLM and varies between runs; a human decides.
- **QuickBooks data is not an input to the analysis.** The sandbox holds Intuit's sample company; the analysis reads the supplied workbook.
- **The MCP server is an untracked, git-ignored clone**, so the connection check is not reproducible from the repo alone.
- **Only wide-sheet workbooks** (one column per month) are supported without code changes.
