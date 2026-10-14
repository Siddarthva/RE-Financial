# 01_connection — QuickBooks MCP connection

**Answers:** Part 1 of the brief — connect Claude to QuickBooks through MCP and show it works, safely.

**What's here**
- `connection_decision.md`, `part1-quickbooks-mcp.md` — why the official read-only MCP server over stdio, status, and how to verify it.
- `dependency_risk.md` — supply-chain notes on the vendored MCP server.
- `.mcp.json.example` — template config; the three `QUICKBOOKS_DISABLE_*` flags are `true`. The real `.mcp.json` and environment files are git-ignored.
- `evidence/quickbooks/` — eight redacted request/response pairs from the sandbox, `checks.json`, and `redact_and_verify.py`.
- `qbo_test_connection.py` — read-only status / `CompanyInfo` test (`python 01_connection/qbo_test_connection.py abc --test`).
- `load_workbook_to_sandbox.py` — sandbox-only loader for the ABC totals (dry-run by default).
- `NETWORK_DIAGNOSTICS.md` — connectivity checks for the Windows machine.

**Status:** the live CompanyInfo test passes — `qbo_test_connection.py abc --test` returned `ok: true` on 2026-10-14 (03:49 UTC); 8 evidence pairs saved.
**What it proves:** a read-only live query worked, secrets never reached the repo (`tests/test_evidence_redaction.py`), and the write path is separate from the read-only server.
**Not proven:** QuickBooks sample data is not an input to the analysis; the workbook is.

## Loading ABC totals into the QuickBooks sandbox (`01_connection/load_workbook_to_sandbox.py`)

A separate write path for the **sandbox only**. It does not use or change the read-only MCP server, its `.env` or the `QUICKBOOKS_DISABLE_*` flags (`CLAUDE.md`: those stay `true`).

- `--dry-run` (default) prints the 18 journal entries (one per month, `ABC-YYYY-MM`, dated month end) and writes `outputs/abc/qbo_load_plan.json`. It needs no credentials and writes nothing.
- `--apply` creates the missing accounts (`Workbook Load - ...`) and entries. It needs a write-scoped env file outside the repo, by default `C:\RE\.secrets\qbo_write.env` (or `--env-file`), with `QBO_WRITE_CLIENT_ID`, `_CLIENT_SECRET`, `_REFRESH_TOKEN`, `_REALM_ID` and `QBO_WRITE_ENVIRONMENT=sandbox`. It refuses production, the MCP `.env` and incomplete files, and saves a rotated refresh token back to its own file.
- Re-runs are safe: an existing `DocNumber` with the same lines is skipped; one with different lines is reported as a `CONFLICT` and left alone.
- `--compare PNL.json` checks a saved QBO monthly P&L (read through the read-only MCP) against the workbook totals and writes `outputs/abc/qbo_vs_workbook.md`.

Only Total Income, Total COGS and Total Operating Expenses are loaded, plus a clearing line so each entry balances. The 70 expense accounts and the Balance Sheet are not. `tests/test_qbo_load.py` runs everything against an in-memory fake; no live write has been done.
