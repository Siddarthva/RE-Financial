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

**What it proves:** a read-only live query worked, secrets never reached the repo (`tests/test_evidence_redaction.py`), and the write path is separate from the read-only server.
**Not proven:** QuickBooks sample data is not an input to the analysis; the workbook is.
