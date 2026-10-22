# QuickBooks sandbox capture, 2026-10-22 (read-only, redacted)

Captured by [`../capture_monthly.py`](../capture_monthly.py): MCP server over stdio with QUICKBOOKS_DISABLE_WRITE/UPDATE/DELETE=true,
`get_profit_and_loss` and `get_balance_sheet` with `start_date=2024-11-01`, `end_date=2026-10-31`, `summarize_column_by=Month`, accrual.
Every response went through `redact_and_verify.redact()` before it was written; the residual secret scan found nothing ([`summary.json`](summary.json)).
The first attempt timed out while the MCP server started; the retry two minutes later passed. Company: Intuit's sample company, **not ABC**.

| File | What it is |
|---|---|
| `01_pnl_monthly_accrual.*` | ProfitAndLoss, 24 month columns + Total. Activity May - Oct 2026 only (Oct month-to-date) |
| `02_balance_sheet_monthly_accrual.*` | BalanceSheet, 24 month-end columns. Balances every month; equity Net Income = YTD P&L net income |

These two files are the input of client `qbo_sandbox` ([`../../../../clients/qbo_sandbox/config.yaml`](../../../../clients/qbo_sandbox/config.yaml)).
