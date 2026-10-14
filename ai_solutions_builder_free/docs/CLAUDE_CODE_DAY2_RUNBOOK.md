# Claude Code Day-2 Runbook — AI Solutions Builder

## Goal
Use Claude extensively for the parts that benefit from Claude: repository inspection, skill design/refinement, MCP verification, commentary quality, evaluation design, architecture critique, and end-to-end demonstration. Do not ask Claude to guess numeric results; Python should compute the metrics and tests should verify them.

## Before starting Claude tomorrow
1. Open PowerShell.
2. Confirm network access and sign in:
   ```powershell
   claude --version
   claude
   ```
3. In the Claude Code session, run `/status` and confirm the intended subscription/account. Do not set `ANTHROPIC_API_KEY` unless deliberately choosing API billing.
4. Open the project:
   ```powershell
   cd C:\RE\ai_solutions_builder_free
   claude
   ```
5. Confirm MCP registration:
   ```powershell
   claude mcp list
   ```
   The `quickbooks` server should appear. The previous session failed to connect to Anthropic (`ECONNRESET`), so check network/account before assuming Pro alone fixes it.
6. Keep QuickBooks read-only. Never enable writes for this assessment unless the brief explicitly requires it.

## First prompt to Claude Code
Paste this after opening Claude Code in the project directory:

> You are helping complete the RE Financial Services “AI Solutions Builder” assessment. First inspect the entire repository and the assessment brief in the project context. Do not overwrite source data or expose secrets. Read README.md, docs/part1-quickbooks-mcp.md, docs/architecture.md, .claude/skills/monthly-financial-analysis/SKILL.md, .claude/skills/skill-catalog.md, src/, tests/, and evals/.
>
> Work in small, verifiable steps. Start by running the existing unit tests and inspecting the actual workbook `ABC Inc - Financial Statements (1).xlsx` (I will place a copy in this project folder). Inspect sheet names, headers, date periods, signs, currency/unit clues, formulas, subtotal rows, and all account categories. Compare the generated analysis with source values. Fix any defects you find in the adapter, especially any risk of including subtotal rows or relying on hidden global state. Add tests for the actual workbook mapping and all important edge cases.
>
> Keep calculations deterministic in Python; use Claude for reasoning, skill authoring, commentary grounded in calculated results, evaluation design, and review. Do not invent business causes, currency, or missing data. Do not claim the QuickBooks connection is end-to-end verified until you call a read-only MCP tool successfully and show the returned sandbox data. The QuickBooks MCP server must remain read-only; `QUICKBOOKS_DISABLE_WRITE`, `QUICKBOOKS_DISABLE_UPDATE`, and `QUICKBOOKS_DISABLE_DELETE` stay true.
>
> Required deliverables: (1) working documented QuickBooks sandbox MCP integration and rationale, (2) reusable SKILL.md that analyzes the 18-month workbook with revenue, gross/net/operating margins where supported, operating expense category trends, MoM and TTM, and grounded commentary, (3) at least five golden evaluation cases plus a repeatable regression command and grading rubric, (4) one-page architecture note covering files/skills/memory, hosting, credential handling, and ten-client tenant isolation. Keep a changelog of changes and list any incomplete requirement explicitly.
>
> Before modifying files, give me a short audit of risks and a prioritized implementation plan. Then implement one stage at a time, run tests after each stage, and summarize changed files and test results.

## Copy the source workbook into the project
Save/copy the supplied workbook as:
`C:\RE\ai_solutions_builder_free\ABC Inc - Financial Statements.xlsx`

Do not place the QuickBooks `.env` file or credentials in this project.

## Current status
- QuickBooks app and sandbox OAuth completed.
- `.env` has Client ID, Client Secret, Refresh Token, and Realm ID.
- MCP registration exists and `claude mcp list` previously reported `quickbooks ... Connected`.
- Write/update/delete flags are true.
- Claude Code itself failed to connect to `api.anthropic.com` with `ECONNRESET`; live Claude/MCP tool invocation is still pending.
- Local scaffold has six passing unit tests in the environment where it was built.
- The ABC workbook adapter runs and emits four output sheets, but it needs a deeper source-vs-output audit before submission.
