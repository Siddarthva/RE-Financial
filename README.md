# AI Solutions Builder — Assessment Scaffold

This project supports the RE Financial Services “Build Exercise — AI Solutions Builder”. The source workbook is treated as read-only. The scaffold can be developed and tested without Claude Pro or Anthropic API billing; Claude Code use itself requires an authenticated supported plan or separately billed API access.

## Where things are
| Folder | What it holds | Brief requirement |
|---|---|---|
| `01_connection/` | QuickBooks MCP decision, redacted evidence, connection and sandbox-load scripts | Part 1: connect safely |
| `02_skill/` | How the monthly-analysis skill works, runs, and scales to new clients; sample outputs | The skill |
| `03_evals/` | Golden cases, commentary grader, mutation test, run records | Evaluation |
| `04_architecture/` | Architecture, workflow, brief traceability | Architecture |
| `05_review_workspace/` | Optional Streamlit review UI (display only) | Optional extra |
| `data/` | Source workbook (read-only) | Input |
| `src/` `tests/` `clients/` `scripts/` `config/` `outputs/` `.claude/` | Engine, unit tests, per-client configs, entry points, templates, generated files, Claude Code setup | Shared |

To build the submission zip: `python scripts/package_submission.py` (scans for secrets first; includes only git-tracked files).

## Project contents
- `src/financial_analysis.py` — deterministic analysis for normalized monthly data, including MoM metrics, margins, category changes, and TTM calculations restricted to consecutive monthly periods.
- `src/run_client.py` — config-driven per-client run: `python src/run_client.py <client>` writes to `outputs/<client>/`.
- `src/client_sandbox.py` — isolation guard: a run can't read another client's folder or outputs, and can only write to its own `outputs/<client>/`.
- `clients/abc/config.yaml` — ABC Inc config: workbook path, sheet names, row labels, OPEX account → category mapping, fiscal year (January start, evidenced by Balance Sheet D63).
- `clients/xyz/` — synthetic 14-month client (Apr 2025–May 2026, April fiscal year, different labels, no Sales & Marketing accounts) and its generator.
- `src/abc_workbook_adapter.py` — engine for wide-format monthly income statements; the defaults reproduce the ABC Inc workbook layout. Its output must be source-validated before submission; don't treat successful export as proof of correct mapping.
- `tests/` — Python unit tests.
- `03_evals/golden_cases.json` — seventeen golden cases: G01–G08 and G14 test synthetic engine rules, and G09–G13 and G15–G17 use the real ABC workbook with source-cell references.
- `03_evals/mutation_test.py` — injects known bugs into a copy of the code and reports which evals catch each one.
- `03_evals/run_golden_evals.py` — repeatable golden-case evaluation runner.
- `03_evals/grade_commentary.py` — commentary grader: every number must match the engine's computed JSON, and the top 3 movements must be named.
- `03_evals/GRADING.md` — how numbers, flags and commentary are scored, and what counts as a regression.
- `03_evals/evals_caught.md` — log of bugs caught by evals and reconciliation.
- `.claude/skills/skill-catalog.md` — catalog and routing guide for all analytical and firm workflow skills.
- `.claude/skills/monthly-financial-analysis/SKILL.md` — monthly workbook analysis: audit, revenue, margins, OPEX, MoM, TTM, cash-flow availability, anomalies, and executive commentary (one skill, numbered sections).
- `.claude/skills/company-context/SKILL.md` — firm context, operating boundaries, and service routing.
- `.claude/skills/financial-statement-tie-out/SKILL.md` — cross-statement arithmetic and balance-sheet equation checks.
- `.claude/skills/fpa-budget-variance/SKILL.md` — actual vs budget/forecast variance analysis.
- `.claude/skills/fractional-cfo-insights/SKILL.md` — evidence-backed decision brief for business owners.
- `.claude/skills/month-end-close-review/SKILL.md` — month-end close checklist and exception log.
- `.claude/skills/sec-reporting-support/SKILL.md` — traceable disclosure support for human review.
- `01_connection/part1-quickbooks-mcp.md` — integration decision, current status, and safe verification procedure.
- `04_architecture/architecture.md` — architecture, hosting, credential handling, and ten-client isolation.
- `01_connection/NETWORK_DIAGNOSTICS.md` — Windows commands to diagnose Anthropic connectivity safely.
- `04_architecture/CLAUDE_CODE_DAY2_RUNBOOK.md` — staged handoff for Claude Code once it is reachable.

## Windows setup and tests
From the project root in PowerShell:

```powershell
py -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python 03_evals\run_golden_evals.py
```

Expected result: all unit tests pass and the golden evaluator reports 17/17. G09–G13 read the real workbook (read-only). Grade commentary with `python 03_evals\grade_commentary.py`; see `03_evals/GRADING.md`. If a case fails, fix the engine or the test contract before claiming success; never edit expected values to pass.

## Per-client runs
```powershell
python src\run_client.py abc
python src\run_client.py xyz
```
Each run reads only `clients/<client>/config.yaml`, the workbook that config declares, and shared code. Outputs go to `outputs/<client>/` (`analysis.xlsx`, `summary.json`, `commentary.md`); `outputs/` is at the repo root. Adding a client means adding a config, not changing code. `tests/test_client_isolation.py` proves one client's run can't read or write the other's folder.

## ABC workbook adapter
The supplied workbook lives in `data/` (read-only). Run:

```powershell
python src\abc_workbook_adapter.py "data\ABC Inc - Financial Statements.xlsx" --output "outputs\ABC_Inc_Financial_Analysis.xlsx"
```

The output is a separate file. Never overwrite or modify the source workbook. The adapter is preliminary until the source-to-output mapping, subtotal handling, and all reported values have been independently validated. Do not spend time polishing the report before the QuickBooks MCP connection is demonstrated end to end.

## Security rules
- Never commit or share `.env`, OAuth tokens, client secrets, authorization codes, or credential-bearing proxy URLs.
- Keep the QuickBooks MCP `.env` in its separate repository; do not copy it here.
- Keep `QUICKBOOKS_DISABLE_WRITE`, `QUICKBOOKS_DISABLE_UPDATE`, and `QUICKBOOKS_DISABLE_DELETE` set to `true`.
- Use only the Intuit developer sandbox and provided fictional workbook, never live client data.
- Store client-specific files, reports, credentials, logs, caches, and model context separately in any future multi-tenant deployment.

## Current integration status
The Intuit app, sandbox OAuth flow, official MCP server build, local MCP registration, and read-only flags have been configured. A live read-only query through Claude Code has not yet been confirmed because Claude Code previously reported a connection reset to `api.anthropic.com`. Follow `01_connection/NETWORK_DIAGNOSTICS.md`; do not describe the connection as fully verified until a real sandbox response is retrieved through an MCP tool.

## Skills architecture and discovery
All seven skills live under `.claude/skills/<skill-name>/SKILL.md`, Claude Code's project-local skill location. Each `description` states when the skill should trigger. The catalog is maintained at `.claude/skills/skill-catalog.md`.

> **Discovery:** Claude Code loads these skills when it is started from the repo root. A headless session run here (Claude Code 2.1.296, 2026-10-12) listed all seven.

`monthly-financial-analysis` covers all monthly analytics in numbered sections (workbook audit, revenue, margins, operating expenses, MoM, TTM, cash-flow availability, variance/anomaly flags, executive commentary); run only the sections a request needs. Skills define workflow and interpretation; deterministic Python code calculates numeric results. Each skill must state when the source data is insufficient rather than inventing missing metrics. The cash-flow section must not fabricate numbers; it states that the assessment workbook contains only the Income Statement and Balance Sheet.

## Business-aligned skill library
The skill library covers the firm's stated assessment context: month-end close, FP&A, fractional CFO, and SEC-reporting support, alongside monthly financial analytics. See `.claude/skills/skill-catalog.md`. The supplied ABC Inc workbook is fictional and must not be represented as the firm's own financial data.

## Safety hooks (`.claude/settings.json`)

Two project hooks enforce rules from `CLAUDE.md`. The scripts are in `.claude/hooks/`.

| Hook | When | What it does |
|---|---|---|
| `guard_secrets.py` (PreToolUse on `Read`, `Grep`, `Bash`) | Before the call runs | Blocks any call naming a file called `.env`, `.env.*`, `*token*` or `*credential*` (`.env.example`, `.sample` and `.template` are allowed). Claude sees the block message and is told to ask you. |
| `test_after_edit.py` (PostToolUse on `Edit`, `Write`, `MultiEdit`) | After an edit to a `.py` file under `src/` | Runs `python -m unittest discover -s tests`. A failure goes back to Claude as feedback; edits elsewhere are ignored. |

**Proof.** `tests/test_hooks.py` covers the secret guard and the post-edit path filter. Both hooks were also run end-to-end through `claude -p` in a scratch project: `Read probe/.env` and `cat probe/credentials.json` were blocked by the hook, and changing a value in `src/` made the post-edit hook report the failing test.

**Limits.**
- The guard matches file names, not contents. In `Bash` it needs a path separator or an extension, so `grep token src` passes but `cat tokens` (no extension) and wildcards such as `cat .e*` do not trigger it.
- It is a safety net next to the `CLAUDE.md` rule, not a sandbox.
- The post-edit hook only fires for edits made through Claude's edit tools, not for files changed by a shell command.

## Monthly analysis with review (`/monthly-analysis <client> <YYYY-MM>`)

Example: `/monthly-analysis abc 2026-06`, run from the repo root in Claude Code. The command is `.claude/commands/monthly-analysis.md`.

1. `python src/monthly_review.py prepare <client> <month>` runs the client's analysis and writes `outputs/<client>/review_packet_<month>.json`, the JSON that commentary is checked against (all months' totals, MoM, TTM, margins; the month's line items; top 3 movements; cash and runway when the client has a Balance Sheet; one-offs; data-quality warnings).
2. Claude drafts a numbered commentary, `commentary_<month>.md`, from the packet only.
3. The `finance-reviewer` subagent (`.claude/agents/finance-reviewer.md`, read-only) checks numbers and direction words against the packet, unsupported claims, missed movements and invented causes. It returns `approve` or a changes list, plus open questions for management. Claude fixes and re-reviews at most once.
4. `python src/monthly_review.py build ...` writes `outputs/<client>/monthly_review_<month>.xlsx`: Summary, Commentary Sign-off (one row per statement, with an empty sign-off column), Numbers Check, Top Movements, Reviewer Changes and Open Questions.

The pack is **APPROVED** only if the reviewer approves *and* the deterministic grader passes (every number matches the JSON, all 3 top movements named, cash risk covered when the client has cash data). The sign-off cells are never filled in for you. `tests/test_monthly_review.py` covers the packet, the verdict rules and the xyz client.

## Loading ABC totals into the QuickBooks sandbox (`01_connection/load_workbook_to_sandbox.py`)

A separate write path for the **sandbox only**. It does not use or change the read-only MCP server, its `.env` or the `QUICKBOOKS_DISABLE_*` flags (`CLAUDE.md`: those stay `true`).

- `--dry-run` (default) prints the 18 journal entries (one per month, `ABC-YYYY-MM`, dated month end) and writes `outputs/abc/qbo_load_plan.json`. It needs no credentials and writes nothing.
- `--apply` creates the missing accounts (`Workbook Load - ...`) and entries. It needs a write-scoped env file outside the repo, by default `C:\RE\.secrets\qbo_write.env` (or `--env-file`), with `QBO_WRITE_CLIENT_ID`, `_CLIENT_SECRET`, `_REFRESH_TOKEN`, `_REALM_ID` and `QBO_WRITE_ENVIRONMENT=sandbox`. It refuses production, the MCP `.env` and incomplete files, and saves a rotated refresh token back to its own file.
- Re-runs are safe: an existing `DocNumber` with the same lines is skipped; one with different lines is reported as a `CONFLICT` and left alone.
- `--compare PNL.json` checks a saved QBO monthly P&L (read through the read-only MCP) against the workbook totals and writes `outputs/abc/qbo_vs_workbook.md`.

Only Total Income, Total COGS and Total Operating Expenses are loaded, plus a clearing line so each entry balances. The 70 expense accounts and the Balance Sheet are not. `tests/test_qbo_load.py` runs everything against an in-memory fake; no live write has been done.
