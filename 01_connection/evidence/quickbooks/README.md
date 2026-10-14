# QuickBooks MCP evidence (sandbox, read-only)

These files were captured on 2026-10-12 from the Intuit **developer sandbox** ("Sandbox Company US a3a1", created 2026-10-10) through the local QuickBooks MCP server. Write, update and delete are disabled on that server, and only `get_*`/`search_*` tools were called.

The sandbox holds Intuit's generated sample data, **not** ABC Inc's figures. Nothing here reconciles to the ABC workbook.

Each call has two files:
- `NN_*.request.json`: the exact tool name and parameters sent.
- `NN_*.response.redacted.*`: the response, verbatim except for redactions.

`checks.json` records each claim below with pass/fail and its supporting values, and `redaction_log.json` lists what was redacted (counts only). The unredacted raw responses were deleted after redaction and are not stored anywhere. To regenerate, recapture the same calls into a folder outside the repo and run `python 01_connection/evidence/quickbooks/redact_and_verify.py <raw_dir>`.

| File | What it proves |
|---|---|
| `01_pnl_2026-01_to_06_monthly_accrual` | The Jan–Jun 2026 monthly P&L request is correct: all six month columns come back. Jan–Apr are 0.00 on every line. May has net income 91.25, June 365.00, total 456.25. |
| `02_pnl_2026-01_to_06_monthly_cash` | On a cash basis, only June has activity: May's 391.25 of income was invoiced but not yet received. |
| `03_pnl_default_no_params` | With no parameters, the tool defaults to "this calendar year-to-date" (1 Jan–12 Oct 2026) as a single Total column. Net income is 1,642.46, so most sample activity falls after June. |
| `04_gl_2026-01_to_04` | The general ledger for Jan–Apr 2026 has no transactions (`NoReportData: true`). |
| `05_gl_2000-01_to_2026-04` | No transactions exist on any date before 1 May 2026. |
| `06_invoices_before_2026-05-01` | No invoices are dated before 1 May 2026. |
| `07_balance_sheet_2026-06-30` | Balance Sheet as of 30 Jun 2026: assets 5,488.75 = liabilities 32.50 + equity 5,456.25. Its net income (456.25) ties to the Jan–Jun P&L total. |
| `08_company_info` | The sandbox company was created on 2026-10-10, with a January fiscal year. Its sample transactions start in May 2026. Email addresses are redacted. |

## Why only May and June showed

**The sandbox has no data before May. It is not a parameter problem.**

The Jan–Jun request returns all six months (file 01), and the ledger and invoice searches confirm there is nothing to show for Jan–Apr (04–06). Intuit generates sandbox sample transactions relative to the company's creation date (10 Oct 2026, file 08), and the earliest dated activity falls in May 2026.

Any view that hides all-zero columns will therefore show only May and June. On a cash basis it would show only June (file 02).

The parameters of the earlier run were not saved, so its exact call can't be reproduced. A call with no parameters wouldn't explain it either, because that returns one year-to-date column, not monthly ones (file 03).

## Redaction

Removed before saving:
- realm and company IDs;
- OAuth access, refresh and ID tokens, JWTs, bearer headers, client secrets and auth codes;
- URLs with embedded credentials or token/realm query strings;
- `/company/<id>` API paths;
- email addresses.

These responses contained no realm IDs, tokens or URLs; the only redactions were 2 email addresses in file 08. `tests/test_evidence_redaction.py` checks two things: the redactor removes each pattern from planted fake values, and no saved file still matches any pattern.

## Re-run on 2026-10-13

Both reports were run again through the read-only MCP (`get_profit_and_loss` with `summarize_column_by: Month`, accrual, 2026-01-01 to 2026-06-30; `get_balance_sheet` with `end_date: 2026-06-30`, accrual). The figures are identical to files 01 and 07, so the earlier files were not replaced:

| Check | Re-run | Saved file |
|---|---|---|
| P&L columns | Jan–Jun 2026 + Total, 6 monthly columns | same (01) |
| Net income Jan–Apr | 0.00 each | same |
| Net income May / Jun / Total | 91.25 / 365.00 / 456.25 | same |
| Balance Sheet total assets = liabilities + equity | 5,488.75 = 32.50 + 5,456.25 | same (07) |
| Balance Sheet net income | 456.25 (ties to P&L total) | same |

One parameter difference: the re-run left out `start_date` on the Balance Sheet. QuickBooks defaulted it to 2026-01-01 and returned the same as-of totals. As a point-in-time report it only needs `end_date`.
