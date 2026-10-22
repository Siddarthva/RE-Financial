# Client config reference: `clients/<id>/config.yaml`

One YAML file per client holds every client-specific fact. The engine has no client names in it. Validation is in `load_config()` (`src/run_client.py`); label lookups are in the intake gate (`src/close_artifacts.py`).

**How "what breaks" was measured:** [`config_break_lab.py`](config_break_lab.py) copies `xyz` (or `abc` for Balance Sheet fields) to a temp folder, damages one field, runs `scripts/run_pipeline.py`, and records the result in [`config_break_lab_results.json`](config_break_lab_results.json) (25 entries including a baseline; re-run it any time, about 40 s; `tests/test_config_break_lab.py` pins four of them). Messages below are abridged from that file. **Stop** = the run exits 1 at the stage shown, writes no analysis, and names the problem. **Warn** = the run completes and the problem is listed in `summary.json` → `warnings`. **Silent** = nothing flags it.

Rule of thumb: a wrong label or format stops the run at **Intake**. A wrong *judgement* (a valid fiscal-year start, a mapping to the wrong category) cannot be detected by code; the reviewer must check it.

## Fields

| Field | Type | Required | abc example | xyz example | What breaks if wrong (observed) |
|---|---|---|---|---|---|
| `client` | string, `[a-z0-9_-]`, equals folder name | yes | `abc` | `xyz` | **Stop** at Intake: "client is 'zzz' but folder is 'xyz'" |
| `display_name` | string | yes | `ABC Inc` | `XYZ Labs Pvt Ltd (synthetic)` | Missing: **Stop**: "missing keys ['display_name']". A wrong name only changes titles |
| `workbook` | path, relative to the config's folder | yes | `../../data/ABC Inc - Financial Statements.xlsx` | `xyz_financials.xlsx` | **Stop**: "Workbook not found: ...". Never point it at a file you may edit; the source is read-only |
| `sheets.income_statement` | string, exact sheet name | yes | `Income Statement` | `P&L` | **Stop**: "Sheet 'Profit and Loss' not found...; sheets present: ['P&L']" (lists the real names) |
| `sheets.balance_sheet` | string, exact sheet name | no | `Balance Sheet` | not set | Absent: cash, runway and Balance Sheet tie-outs are "not available", not zero. Present but wrong: **Stop**: "Sheet 'BS' not found" |
| `layout.header_label` | string, text in the month-header row | yes | `Account` | `Line Item` | **Stop**: "header row with 'Account' not found in rows 1-15" |
| `layout.month_format` | `strptime` format of the month header cells | yes | `"%b %Y"` (Jun 2026, newest first) | `"%b-%y"` (Apr-25, oldest first) | **Stop**: "no column for 2026-05 ... months found: - to -". Column order does not matter |
| `sections.<id>.header` | string, row label that opens the section | yes, 3 sections | `Income` | `Revenue` | **Stop**: "Section header matched: Sales ... no lines found". (Was Silent before 2026-10-15; the lab found it and an intake check now stops it) |
| `sections.<id>.total` | string, row label that closes the section | yes, 3 sections | `Total Income` | `Total Revenue` | **Stop**: "section total row 'Total Sales' not found" |
| `sections` ids | exactly `income`, `cost of goods sold`, `operating expenses` | yes | as shown | as shown | Missing or extra id: **Stop**: "sections must define exactly [...]" |
| `totals.<key>` | string, row label of that total | yes, 6 keys | `revenue: Total Income` ... `net_income: Net Income` | `gross_profit: Gross Margin`, `net_income: Net Profit` | Wrong label: **Stop**: "total row 'Turnover' (revenue) not found". Missing key: **Stop**: "totals must define exactly [...]" |
| `totals` keys | exactly `revenue`, `cost_of_goods_sold`, `gross_profit`, `operating_expenses`, `operating_income`, `net_income` | yes | as shown | as shown | See above. Intake also checks gross profit = revenue − COGS and operating income = gross profit − opex in every month |
| `subtotal_rows` | list of row labels inside OPEX that are block headers or subtotals | yes (`[]` if none) | `[S & M Payroll, Total S & M Payroll, Marketing, Total Marketing]` | `[]` | Not a list: **Stop**: "wrong types ['subtotal_rows']". A subtotal left out is **counted as a detail line**, double-counting its children; intake then fails "X foots to its lines" in the affected months |
| `categories` | list of reporting category names | yes | 6 names | 5 names | A category an account maps to but not declared: **Stop**: "undeclared categories ['Technology']". A declared category with no accounts: **Warn** "no 'Insurance' accounts in the source; reported as not available, not zero" |
| `account_to_category` | map: exact account label → category | yes | 70 entries | 8 entries | Missing entry: **Warn** "Unmapped OPEX account (reported under 'Unmapped')". Misspelt key: **Warn** twice (unmapped, and "Mapped account not found in workbook"). Mapped to the *wrong but declared* category: **Silent**; the reviewer must approve the mapping |
| `fiscal_year.start_month` | integer 1-12 | yes | `1` | `4` | 13 or text: **Stop**: "must be an integer 1-12". A wrong valid month: **Silent**; fiscal-year labels and FYTD shift. abc's value is evidenced by Balance Sheet D63 Current Year Earnings = Jan-Jun net income |
| `thresholds.gross_margin_drop_pp` | number ≥ 0, percentage points | no | `5` | not set | Absent: no gross-margin flags. Text or negative: **Stop**: "must be a non-negative number" (was an unhandled `TypeError` before 2026-10-15) |
| `thresholds.materiality.min_dollars` / `min_pct` / `sign_flip_dollars` | numbers ≥ 0 (`min_pct` is a fraction: 0.10 = 10%) | no | `5000` / `0.10` / `1000` | not set (engine defaults) | Unknown name: **Stop** at Calculate: "Unknown materiality setting(s) ... Use min_dollars, min_pct and sign_flip_dollars". Negative: **Stop**. Too high a value silently hides flux items; too low floods the reviewer, which is a judgement |
| `balance_sheet_rows` | map: `total_assets`, `total_liabilities_equity`, `current_year_earnings` → row label | no (defaults are ABC's labels) | not set | not set | Needed when a client's Balance Sheet labels differ. A wrong label: **Stop**: "Balance Sheet rows present ... missing Sum of Assets" |
| `layout.type` | `wide` or `long` | no (default `wide`, so existing configs are unchanged) | not set | not set | Other value: **Stop**: "layout.type must be one of ['wide', 'long']". `long` = one row per (account, month); see the long rows below. Examples: `clients/c08`, `clients/c09` |
| `layout.columns` (long only) | map `account`, `month`, `amount`, optional `section` → column header text | yes when `long` | - | - | Missing: **Stop** "layout.columns". Configured column not in the sheet: **Stop** "column 'Amount' (amount) not found". A sheet column that is not configured: **Stop** "unknown column 'Memo' at E1". Duplicate (account, month): **Stop** "appears twice, in rows 5 and 8". A month missing for one account: **Warn** "blank cell(s) ... (no row)", kept as missing, not zero. Unknown section label: **Stop** |
| `source` | `workbook` (default) or `qbo` | no | not set | not set | `qbo`: `workbook` is the saved ProfitAndLoss report JSON (monthly columns) and `balance_sheet_file` the BalanceSheet JSON, read by `src/qbo_adapter.py`; `sheets.*` are the report names. Report-shape change: **Stop** with the cause named. Example: `clients/qbo_sandbox` |
| `balance_sheet_file` (qbo only) | path to the BalanceSheet report JSON | yes when `source: qbo` and a Balance Sheet is used | - | - | Missing: **Stop** at config load |
| `qbo.other_groups`, `qbo.trim_leading_zero_months` (qbo only) | list of top-level group headers expected outside the sections; boolean (default true) | no | - | - | A top-level group not in the sections or this list: **Warn** "is not mapped to a section". Leading months with no activity are left out and named in a warning |
| `cash_row` | row label of month-end cash on the Balance Sheet | no (default `Total Cash and Cash Equivalents`) | not set | not set | Wrong label: cash step fails with a KeyError naming the row |

## Workbook shape the config describes

The config only *names* things; the sheet must already have this shape (from the teammate test, `teammate_test.md`, where the shape had to be guessed from a data file). Template: `clients/xyz/xyz_financials.xlsx`, built by `clients/xyz/generate_dataset.py`; `clients/lmn/generate_dataset.py` is a second example. Treat both generators as templates you may copy.

```text
     A                       B          C          D        ...   one column per month
 1   Title text (ignored)
 2   Subtitle (ignored)
 3   (blank)
 4   <layout.header_label>   Apr-25     May-25     Jun-25         <- header row: anywhere in rows 1-15;
 5   <sections.income.header>                                        month cells text or real dates that
 6   Subscription Revenue    820870.66  851450.36  ...              match layout.month_format
 7   Implementation Fees     170288.13  0          ...           <- detail lines: label in the same column
 8   <sections.income.total> 991158.79  ...                          as the header label
 9   <sections.cost of goods sold.header>   (blank in month columns)
 ..  detail lines, then <...total>
 ..  <totals.gross_profit>
 ..  <sections.operating expenses.header>, detail lines, <...total>
 ..  <totals.operating_income>, <totals.net_income>
```

Rules: section header rows have **no numbers**; amounts are numbers (not text), and total rows are values or formulas **with cached values** (a file written by `openpyxl` formulas has none; open and save it in Excel, or write values; otherwise intake stops with "formulas saved without cached values"); each section's detail lines must add up to its total in every month; months are unique; TTM needs 12 **consecutive** months ending in the reporting month you pass to `run_pipeline.py`. Category names are free text: reusing a name for many accounts is how mapping works, and whether an account belongs there is a judgement the code cannot check.

## Not in the config (code, by design)

Three source shapes are supported: a **wide sheet** (one column per month, sections running header row → detail rows → total row), a **long sheet** (`layout.type: long`, one row per account and month), and **QuickBooks report JSON** (`source: qbo`). Other shapes (one sheet per month, merged headers) cannot be expressed here; the intake gate refuses them, and supporting them is an engine change. Source data kept outside `clients/<id>/` must be listed with its owning client in `clients/data_owners.yaml`; the sandbox blocks every other client from reading it.

## Minimal valid config

The smallest working file is `clients/xyz/config.yaml` (no Balance Sheet, no thresholds, no subtotals): 8 account mappings and 5 categories. Copy it, change the labels to match the new workbook, and run `python scripts/run_pipeline.py <id> <YYYY-MM>`. The intake gate tells you which label it could not find, with the sheet and the row range it searched.
