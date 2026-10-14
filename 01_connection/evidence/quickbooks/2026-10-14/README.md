# QuickBooks sandbox checks, 2026-10-14 (read-only)

Phase 1 re-verification. Every file here is redacted; nothing identifies the company, realm or tokens. Times are UTC.

| # | Check | How | Result | When |
|---|---|---|---|---|
| a | CompanyInfo over stdio MCP | `python 01_connection/qbo_test_connection.py abc --test` (exit 0) | **PASS**: "Connected. Read-only CompanyInfo query succeeded." Saved to `outputs/abc/qbo_status.json` | 04:34:12 |
| b1 | Monthly P&L, Jan-Jun 2026 (accrual) | `capture_dated.py` → `02_pnl_…` | **PASS**: six monthly columns, Jan-Jun 2026 | 04:35:40 |
| b2 | Balance Sheet at 30 Jun 2026 | `capture_dated.py` → `03_balance_sheet_…` | **PASS**: total assets 5,488.75 = total liabilities and equity 5,488.75 | 04:35:47 |
| c | Read-only enforcement | `capture_dated.py` → `01_tools_list.response.json` | **PASS**: 71 tools are registered with the three disable flags set to true, and none is a create/update/delete tool. A "create an invoice" request has no tool to call. | 04:35 |
| d | Failure message: server folder missing | `QBO_MCP_SERVER_DIR=C:/RE/__no_such_server__ python 01_connection/qbo_test_connection.py abc --test` | **PASS**: exit 1, cause `server_missing`. The message names the missing folder and gives the clone/build/auth steps. | 04:34:12 |

The same session's Claude Code MCP tools (`get_profit_and_loss`, `get_balance_sheet`) returned the same figures as (b1) and (b2).

**How (c) is enforced.** The server's `src/helpers/register-tool.ts` skips registering any `create_`/`update_`/`delete_` tool when `QUICKBOOKS_DISABLE_WRITE`/`_UPDATE`/`_DELETE` is `true`. So the server refuses a write before any call can reach QuickBooks. No write was attempted: `CLAUDE.md` forbids calling create/update/delete tools, so the evidence is that no such tool is registered, not a refused call.

**What the data shows.** For Jan-Jun 2026 the sandbox holds only Intuit's sample transactions. Income is 0.00 for Jan-Apr, 391.25 in May and 365.00 in Jun. None of the `Workbook Load - …` accounts exist yet. So the ABC workbook has **not** been loaded into the sandbox (stretch goal not done). `outputs/abc/qbo_vs_workbook.md` was regenerated from (b1) with `load_workbook_to_sandbox.py --compare` and says so.

Re-run: `python 01_connection/evidence/quickbooks/capture_dated.py`. It exits 1 if any check fails or a secret-like pattern survives redaction. `summary.json` holds the checks and the redaction counts.
