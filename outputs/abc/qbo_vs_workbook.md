# QBO vs workbook

QBO P&L: `02_pnl_2026-01_to_06_monthly_accrual.response.redacted.json`. Workbook: ABC monthly totals.

| Metric | Month | Workbook | QBO | QBO - workbook | Note |
|---|---|---|---|---|---|
| revenue | all | None | None | None | account 'Workbook Load - Total Income' not in the QBO P&L |
| cost_of_goods_sold | all | None | None | None | account 'Workbook Load - Total COGS' not in the QBO P&L |
| operating_expenses | all | None | None | None | account 'Workbook Load - Total Operating Expenses' not in the QBO P&L |

## Structural differences (by design)

- Operating expenses are one line in QBO (3 loaded accounts): the workbook's 70 expense accounts, categories, one-off detection and top movements cannot be reproduced from QBO.
- Gross profit, operating income and net income are derived in QBO from the three loaded accounts and equal the workbook only if those totals tie.
- The sandbox company has its own sample transactions (from May 2026); compare only the 'Workbook Load - ...' accounts, never the company total.
- The Balance Sheet, cash and runway are not loaded; the clearing account carries the cumulative net result and has no workbook counterpart.
- TTM and month-over-month figures need 12 and 2 loaded months respectively; a partial load withholds them exactly as the workbook analysis does.
