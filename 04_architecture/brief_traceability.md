# Brief traceability

Source: "Build Exercise — AI Solutions Builder" (RE Financial Services), the PDF supplied with the exercise. Status is **Done**, **Partial** or **Not done**, judged against the brief's own wording. Reasons are deliberately blunt. Commands run from the repo root.

## Part 1 — Connect the QuickBooks sandbox to Claude

| Requirement | Where | Status | Reason |
|---|---|---|---|
| Connect securely and reliably (native connector, open-source MCP, or custom MCP) | `01_connection/connection_decision.md`, `01_connection/.mcp.json.example` | **Done** | Official Intuit MCP server over stdio. Write, update and delete flags are `true`. Secrets stay outside the repo; hooks and the secret scan enforce it. |
| Demonstrate it working against the sandbox | `01_connection/evidence/quickbooks/`, `01_connection/qbo_test_connection.py` | **Done** | Eight live read-only calls (P&L, GL, balance sheet, company info) are saved with secrets redacted (2026-10-12). A retest on 2026-10-13 had failed; that was a bug in `qbo_test_connection.py` (it sent no `params`, which the server's input check rejects), not an expired token. Fixed. `qbo_test_connection.py abc --test` on 2026-10-14 (03:49 UTC) returned `ok: true`, live read-only CompanyInfo query succeeded; 8 evidence pairs saved. Re-checked 2026-10-14 04:34–04:36 UTC (CompanyInfo, monthly P&L, Balance Sheet, tool list): `01_connection/evidence/quickbooks/2026-10-14/`. |
| Document what was chosen, what was rejected, and why | `01_connection/connection_decision.md`, `01_connection/part1-quickbooks-mcp.md` | **Done** | Native connector and custom MCP are rejected with reasons. `part1-quickbooks-mcp.md` still contains an older "not yet demonstrated" paragraph about a Claude connection error; a note at its top says it is out of date. |
| Where it would run if a whole team needed it | `01_connection/connection_decision.md` ("Team hosting") | **Partial** | Written as a design only and labelled Proposed. The server has no network transport, so a shared service would need a wrapper that does not exist. |
| How credentials are handled throughout | `01_connection/connection_decision.md` ("Credential flow"), `.claude/hooks/guard_secrets.py`, `scripts/scan_secrets.py`, `01_connection/dependency_risk.md` | **Done** | Hook blocks reads of environment and token files. Evidence is redacted and tested. The audit found 49 npm vulnerabilities, 3 in runtime dependencies, all classed unreachable over stdio; none were fixed. The hook matches file names, not contents. |

## Part 2 — Monthly trend analysis skill

| Requirement | Where | Status | Reason |
|---|---|---|---|
| Revenue, margins, operating expenses by category | `.claude/skills/monthly-financial-analysis/SKILL.md`, `src/abc_workbook_adapter.py` | **Done** | Computed by code from the supplied workbook; golden cases pin the Jun 2026 summary. |
| Month-over-month and trailing-twelve-month views | `src/financial_analysis.py`, `03_evals/golden_cases.json` | **Done** | TTM is withheld ("not available") before Dec 2025, the first month with 12 months of history. |
| Short commentary flagging movements an owner should know | `/monthly-analysis`, `02_skill/sample_outputs/commentary_2026-06.md` | **Done** | Numbered statements; every number is checked against the engine output by the grader. Whether a statement is worth making is judged by an LLM reviewer and a human, not by code. |
| For a human reviewer to finish | `src/monthly_review.py`, `02_skill/sample_outputs/monthly_review_2026-06.xlsx` | **Done** | Excel pack with a blank sign-off column and open questions. |
| Readable, maintainable, extensible by a teammate | `.claude/skills/`, `02_skill/README.md`, `tests/` | **Done** | Skill, engine, config and tests are separate; the README gives the three-step add-a-client recipe. |
| Point at a different company's data without a rewrite | `clients/xyz/config.yaml`, `tests/test_client_isolation.py` | **Partial** | `xyz` (different labels, fiscal year, date format) runs with a config only. The parser still assumes one wide sheet with month columns; a differently shaped export would need code. |
| **Stretch:** load the workbook into the sandbox and run the skill end-to-end through the live connection | `01_connection/load_workbook_to_sandbox.py`, `outputs/abc/qbo_load_plan.json` | **Not done** | The loader and an 18-entry dry-run plan exist and are tested. No live write has been done (the loader's tests use an in-memory fake), and the comparison (`outputs/abc/qbo_vs_workbook.md`, re-run 2026-10-14 against that day's live P&L) finds no loaded accounts. The skill reads the workbook, not QuickBooks. A QuickBooks P&L could not reproduce the workbook's 70 expense accounts anyway. |

## Part 3 — Evals

| Requirement | Where | Status | Reason |
|---|---|---|---|
| At least five golden cases (data state plus expected output) | `03_evals/golden_cases.json`, `03_evals/run_golden_evals.py` | **Done** | 18 cases by `source`: `workbook` 4 (G01, G02, G03, G06), `workbook+perturbation` 5 (G04, G05, G07, G08, G14), ABC cell-sourced 9 (G09–G13, G15–G18). Expected values for the real-workbook cases were derived by hand from source cells, not from the adapter. |
| How the system is graded | `03_evals/GRADING.md`, `03_evals/grade_commentary.py` | **Done** | Three graders: numbers, commentary (numbers, top-3 movements, cash risk), and mutation. |
| How a regression is detected after a change | `03_evals/mutation_test.py`, `scripts/export_eval_results.py`, `.claude/hooks/test_after_edit.py` | **Done** | 13 injected bugs must each fail a test or case. The post-edit hook reruns unit tests after edits under `src/`. There is no CI service; the checks run on demand. |
| Grading quality of the commentary itself | `03_evals/GRADING.md` | **Partial** | Numbers and coverage are graded; tone, usefulness and causal reasoning are not. |

## Part 4 — One-page architecture note

| Requirement | Where | Status | Reason |
|---|---|---|---|
| Project structure: files, skills, memory | `04_architecture/architecture.md` | **Done** | Covers structure and a Memory section. The note is 614 words (38 Markdown lines, some long; `wc -w`). Not checked as a printed page. |
| Hosting choices | `04_architecture/architecture.md` ("Hosting") | **Done** | One Windows machine, implemented; shared hosting is Proposed. |
| What changes at ten clients, and keeping each client's data separate | `04_architecture/architecture.md` ("Ten-client isolation") | **Partial** | Per-client config and output folders with an in-process audit hook are implemented and tested with two clients. Per-client OAuth grants, processes and OS accounts are Proposed. The hook covers this Python process only, not Claude's own tools. |

## Deliverables

| Deliverable | Where | Status | Reason |
|---|---|---|---|
| The working connection (config, deployed server, or code) | `01_connection/` | **Partial** | Config template, scripts and evidence are in the repo. The MCP server itself is Intuit's repository, cloned beside the repo and not tracked, so it is not in the submission zip. A reviewer must clone it, build it and run the OAuth step. |
| The skill file(s) | `.claude/skills/`, `.claude/commands/`, `.claude/agents/` | **Done** | Seven skills, one command, one reviewer agent. The monthly analysis skill is the one the brief asks for. |
| Eval cases and grading approach | `03_evals/` | **Done** | See Part 3. |
| One-page architecture note | `04_architecture/architecture.md` | **Done** | See Part 4. |

## Final-round readout topics

| Topic | Where | Status | Reason |
|---|---|---|---|
| Demo the sandbox connection and the trend analysis, real system not slides | `01_connection/`, `README.md` quickstart, `05_review_workspace/` | **Done** | The trend analysis runs offline in about a minute. The live CompanyInfo test passed on 2026-10-14 (03:49 UTC, `ok: true`), so a live demo is possible on the machine that holds the sandbox authorization. |
| One small modification on the spot | `02_skill/README.md`, `clients/`, `tests/` | **Done** | Rehearsed 2026-10-14: gross-margin drop flag over 5 pp (config threshold, engine flag, golden case G18, unit test) in its own commit `demo: flag gross-margin drops over 5 pp`, about 4 minutes. Log: `03_evals/evals_caught.md`, "Rehearsed modification". |
| Why it is structured this way | `04_architecture/architecture.md`, `04_architecture/workflow.md` | **Done** | Written down, with Implemented and Proposed labelled. |
| What the evals caught while building | `03_evals/evals_caught.md` | **Done** | A log of defects found by evals and reconciliation. |
| What breaks first at ten clients | `04_architecture/architecture.md` ("What breaks first") | **Done** | Six items, led by credential upkeep and isolation being a convention rather than a boundary. |

## Ground rules

| Rule | Where | Status | Reason |
|---|---|---|---|
| Only the developer sandbox and the supplied workbook; no live accounts or real data | `CLAUDE.md`, `clients/xyz/` | **Done** | The `xyz` client is synthetic. QuickBooks is the Intuit sandbox with write tools disabled. |
| Explain every choice as your own | `01_connection/connection_decision.md`, `04_architecture/architecture.md` | **Partial** | The reasoning is written down. Being able to explain it live is up to the person presenting. |
