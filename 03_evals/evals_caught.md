# Bugs caught by evals and reconciliation

Log of defects found by checking engine output against source cells or by tests. Each entry has a regression test.

## 2026-10-12 — `src/abc_workbook_adapter.py` reconciliation against `ABC Inc - Financial Statements.xlsx`

**How it was found:** read-only cell-by-cell reconciliation of adapter output against the workbook. Checked Jan 2025, Jun 2025, and Jun 2026 (246 checks), then all 18 months (1,476 checks): revenue streams, total revenue, COGS, gross profit, all 70 OPEX detail categories, sum of categories vs Total Operating Expenses, and net income. **All values matched before and after the fixes.** The bugs below are in derived output and in logic that this workbook's layout happens not to trigger.

| # | Bug | Effect | Fix | Regression test |
|---|---|---|---|---|
| 1 | **Sign:** `generate_commentary` computed MoM % as `change / prior`. With a negative prior value, the % had the opposite sign to the $ change. | Shipped output said `Net income … change +8,343.52 (-2.5%)` for Jun 2026 (C107 −330,756.08 vs D107 −339,099.60), even though the loss shrank. | Divide by `abs(prior)` (the rule in the monthly-financial-analysis skill). Output now reads `(+2.5%)`. | `test_bug1_mom_pct_sign_uses_absolute_prior_for_negative_base` |
| 2 | **Hidden global:** `build_expense_category_trends` re-read the workbook through a module global `INPUT_PATH` that only `analyze_wide_workbook` set. | Any direct call (tests, notebooks, other pipelines) raised `NameError: name 'INPUT_PATH' is not defined`. | The parser records each row's section in `account_month.attrs["sections"]`. Category trends use that map and no longer re-read the file or use a global. | `test_bug2_expense_trends_do_not_depend_on_module_global` |
| 3 | **Row mapping:** the OPEX section's stop condition looked for `Total Operating Expenses` in the Account column (B). The source puts it in column A (A103), so the stop never fired. | Any non-excluded account row after Total OPEX (e.g. "Other Income") would be counted as an operating expense. This workbook was saved only because `Operating Income`/`Net Income` are on the exclude list. | Section boundaries are tracked in the parser from the section header row to its `Total <section>` row, whichever column the label is in. | `test_bug3_rows_after_total_operating_expenses_are_not_opex` |
| 4 | **TTM continuity:** `build_monthly_summary` `*_ttm` columns were plain 12-row rolling sums with no calendar check. | A workbook with a missing month would report a TTM figure that is not twelve consecutive months. This workbook (Jan 2025–Jun 2026, no gaps) was unaffected. | Mask TTM unless the 11 preceding month steps are each exactly one calendar month, matching `financial_analysis.normalize_monthly`. | `test_bug4_summary_ttm_requires_consecutive_calendar_months` |

**Source-workbook regression checks added** (`SourceWorkbookReconciliationTests`, read-only, skipped if the workbook is absent):
- months parse as Jan 2025–Jun 2026, ascending, no gaps (the source columns run newest first);
- OPEX categories sum to Total Operating Expenses in every month (guards against subtotal double-counting: `Total S & M Payroll`, `Total Marketing`);
- subtotal and header rows never appear as categories;
- spot cells C14, C107, C31 (negative Bad Debts sign preserved).

**Verification after fix:** 16/16 unit tests and 8/8 golden evals pass. Reconciliation is still 1,476/1,476. TTM revenue for Dec 2025 (2,145,316.28 = SUM I14:T14) and Jun 2026 (2,303,975.51 = SUM C14:N14) match independent sums of the source cells. The source workbook's SHA-256 is unchanged.

## 2026-10-12 — ABC golden cases G09–G13 and commentary grader

| # | Bug | Effect | Fix | Regression test |
|---|---|---|---|---|
| 5 | **Sign:** `build_expense_category_trends` `mom_pct` used signed `pct_change()`. Found by G12. | Income Tax Benefit Jan 2026 (I101 −1,244,429.84 → H101 0) showed `mom_change` +1,244,429.84 with `mom_pct` **−100%**. | Divide `mom_change` by `abs(prior)`; null when the prior is 0. | `test_bug5_category_mom_pct_sign_uses_absolute_prior`, G12 |
| 6 | **Skill guidance gap:** section 9 asked only for top *expense* movements. Found by the commentary grader. | Skill run 1 left out Usage Fees (C11−D11 = −11,142.74), the 3rd-largest line movement in Jun 2026. | Section 9 now asks for the top 3 movements across revenue, COGS and OPEX lines. Run 2 passes 3/3. | `grade_commentary.py --run-skill` |
| 7 | **Engine commentary coverage:** `generate_commentary()` names only totals. Found by the commentary grader. | 0/3 top movements named. | **Not fixed** — open item. | `grade_commentary.py` (default mode) |

Data findings recorded in G10 (not bugs): Income Tax Benefit (row 101) is booked inside Operating Expenses. That is why Dec 2025 OPEX is negative (I103 −402,142.09) and net income is positive. Treat it as a mapping question for the reviewer.

## 2026-10-12 — Mutation testing (`03_evals/mutation_test.py`)

The first run caught 9 of 10 mutants. **Gap:** shifting every month forward by one in `financial_analysis.normalize_monthly` survived. Every synthetic test checked only relative values (diffs, rolling sums, margins), and none asserted that a value stays attached to its own month. **Added** golden case G14 (month labels kept intact through normalization). The re-run caught 10 of 10.

Thin coverage worth knowing (caught, but by a single eval): adapter gross-margin denominator (G13 only); `financial_analysis` category drop (G06 and `test_category_mom`, both single-category inputs).

## 2026-10-12 — Per-client config and isolation

| # | Bug | Effect | Fix | Regression test |
|---|---|---|---|---|
| 8 | **Isolation bypass via path spelling** (new sandbox, caught by its own test before release) | Windows short 8.3 names (`SIDDAR~1`) and long names compared unequal. A tampered ABC config pointing at `../xyz/xyz_financials.xlsx` was **read**; the run failed later only on a sheet-name mismatch. | Compare `realpath`-normalised paths, which also resolves symlinks. | `test_config_pointing_at_other_client_data_is_rejected`, `test_short_and_long_path_spellings_cannot_bypass_the_guard` (both confirmed failing with the old normalisation) |
| 9 | **Shared temp dir** | openpyxl stages files in the system temp folder, which every client's run shares. The sandbox blocked it. | Each run gets a private temp dir at `outputs/<client>/.tmp`, removed afterwards. | `test_each_run_writes_only_its_own_output_folder` |

**Known, not fixed (out of scope — `src/financial_analysis.py`):** `category_summary` `expense_mom_pct` has no zero-denominator guard and can return `inf`.

## 2026-10-13 — re-check of `src/abc_workbook_adapter.py` against the workbook

**How it was checked:** read-only. Recomputed Income (rows 8–13), COGS (17–23), GP, OPEX (29–46, 48–58, 61–70, 72–102, so the subtotal rows 59/71 are skipped) and NI from detail cells for all 18 columns (C=Jun 2026 … T=Jan 2025). Compared each value with the cached total cell and with adapter output. Also checked BS row 63 Current Year Earnings in each of the 18 months against calendar-YTD adapter NI.

**Result: no new bugs.** There were 0 mismatches in 90 total checks, and the 70 OPEX detail categories summed to Total Operating Expenses every month. All 18 Current Year Earnings checks tied, including D63 −1,987,916.44 = Jan–Jun 2026 NI. The traps are handled: the newest-first columns are re-sorted, the empty block-header rows are skipped, and Interest Income and Income Tax Benefit are kept in OPEX as negatives (Dec 2025 OPEX is −402,142.09). The negative Mar 2026 revenue lines F9 −1,608.09 and F12 −550.00 are summed as they are. No code changes, so no new regression tests.

## 2026-10-13 — eval harness

| # | Bug | Effect | Fix | Regression check |
|---|---|---|---|---|
| 10 | **Mutation copy incomplete:** `03_evals/mutation_test.py` copied `src/ tests/ 03_evals/ clients/` but not `evidence/`. `tests/test_evidence_redaction.py` imports `01_connection/evidence/quickbooks/redact_and_verify.py`. | The runner's unmodified-copy baseline failed (`test_evidence_redaction`), so it refused to run any mutants. | Copy `evidence/` as well. | `mutation_test.py` baseline green; 10/10 mutants caught |
| 11 | **G11 too weak:** the runner checked only that Nov 2025 TTM was null. | A TTM leaking into Jan–Oct 2025, or into a non-revenue metric, would have passed. | The runner now requires every month before the first valid one to be null for all five TTM metrics. G11's expected values are unchanged. | G11 |

## 2026-10-13 — final run

| # | Bug | Effect | Fix | Regression check |
|---|---|---|---|---|
| 12 | **Mutation copy missing `scripts/`:** `tests/test_qbo_load.py` imports `01_connection/load_workbook_to_sandbox.py`, but `mutation_test.py` did not copy `scripts/`. Same class as #10. | First clean run: the mutation runner refused to start (`Baseline is not green … test_qbo_load`, exit 2). | Copy `scripts/` too. | Mutation run in `03_evals/FINAL_RUN.md` |
| 13 | **Realistic-looking fake realm ID in a test fixture:** `tests/test_evidence_redaction.py` used a 16-digit value shaped like a sandbox realm ID. | It could not be told apart from a real ID by a reader or a scanner. | Replaced with `1234567890123456`; the fixture is declared a fake fixture to `scripts/scan_secrets.py`. | `tests/test_scan_secrets.py`, `tests/test_evidence_redaction.py` |
| 14 | **Sandbox failed on a fresh checkout:** `client_sandbox` created `outputs/<client>/.tmp` after it started blocking writes, so with no `outputs/` folder yet it blocked its own `mkdir`. | `run_client.py` and the whole mutation baseline failed anywhere `outputs/` did not already exist (a reviewer's first run). Hidden here because `outputs/` already existed. | Create the folder before the sandbox activates. | `test_run_works_when_outputs_folder_does_not_exist_yet` |

## 2026-10-13 — the grader caught stale/contradictory commentary

**How it was found:** `03_evals/FINAL_RUN.md` recorded `grade_commentary.py` FAIL on two of three inputs. The grader was not changed; the commentary was.

| # | Bug | Effect | Fix | Regression check |
|---|---|---|---|---|
| 15 | **Engine commentary incomplete:** `generate_commentary(monthly)` only saw monthly totals, so it could not name line items or cash. | Engine text failed: top movements 0/3, cash risk not covered (Jun 2026 cash 713,481.26 and runway never stated). | `generate_commentary(monthly, account_month, cash)` now names the top 3 latest-month movements by absolute $ change (same ranking as the review packet) and states cash plus 3-month runway (3.4 months, 209,656.62/month burn; the G17 method via `cash_position`). `run_client.py` and the grader's engine path pass these inputs; grading rules unchanged. | `test_engine_commentary_passes_grader_on_real_workbook` |
| 16 | **Skill contradicted the engine:** `monthly-financial-analysis/SKILL.md` §7 said runway "cannot be calculated without fabricating data", while `cash_position()` and golden G17 compute it from Balance Sheet cash. | Saved skill output (`outputs/skill_commentary.md`) repeated that runway can't be calculated; numbers 43/43 and top movements 3/3 but cash risk not covered, so FAIL. | §7 rewritten: cash and runway come from Balance Sheet cash (3-month window, G17); only CFO/CFI/CFF remain unavailable. Skill output regenerated with `grade_commentary.py --run-skill`. | Same test asserts SKILL.md no longer says runway cannot be calculated; `--run-skill` now PASS. |

## 2026-10-14 — Rehearsed modification

**Request (self-set):** "flag gross-margin drops over 5 pp." Not a bug; a rehearsal of the on-the-spot change from the brief.

- **Time taken:** about 4 minutes from first read of the code (03:49:54 UTC) to the passing commit, including a ~1.5 minute unit-test run. One slip on the way: the first G18 expected value compared March 2025 with the wrong prior column; the engine disagreed, the case's own expected value was corrected from cells S14/S26 (a new case, not an existing eval).
- **Files touched (6, commit `demo: flag gross-margin drops over 5 pp`):**
  - `clients/abc/config.yaml`: `thresholds.gross_margin_drop_pp: 5`
  - `src/abc_workbook_adapter.py`: `margin_drop_flags()`
  - `src/monthly_review.py`: threshold read from config, `gross_margin_flags` added to the review packet
  - `03_evals/golden_cases.json`, `03_evals/run_golden_evals.py`: golden case G18 (flags exactly 2025-03, 2025-08, 2026-04, hand-computed from rows 14 and 26)
  - `tests/test_monthly_review.py`: `test_gross_margin_drop_flags`
- **Result:** golden 18/18, unit 102/102.

## 2026-10-14 — clean-state re-verification (Phase 1)

`outputs/` was moved aside and regenerated from scratch. Details: `04_architecture/verification_matrix.md`.
- **Stale committed output:** `outputs/abc/review_packet_2026-06.json` lacked `gross_margin_flags`; the rehearsed modification never regenerated it. Regenerated.
- **Test-order dependency:** `tests/test_ui_numbers.py` crashed on a clean `outputs/` (no `commentary_grade.json` yet). Missing global files now shrink the allowed set instead.
- **False-clean secret scan:** `scripts/scan_secrets.py` given file paths scanned 0 files and reported 0 findings; a misspelt path also passed. Fixed; `test_file_paths_are_scanned_and_missing_paths_fail`.
- **Failed connection test reported success:** `qbo_test_connection.py --test` exited 0 on failure, and the review UI gates on the exit code. Now exits 1.
- **Result:** unit 103/103, golden 18/18, mutation 13/13 (first run since G18).
- **Independent reviewer:** `tests/test_qbo_load.py` `--apply` test wrote the real `outputs/abc/qbo_load_plan.json` before failing on the missing env file. The loader now fails before any side effect; the test uses a temp output root and asserts it stays empty (fails without the fix).

## Robustness (2026-10-14, Phase 2: `03_evals/robustness/fault_injection.py`)

32 faults were injected into copies of the workbook and run through both entry points. Before the fixes, the skill path scored 9/32, with 8 SILENT-WRONG (`03_evals/robustness/BEFORE_FIX.md`). After: 32/32 on both paths (`ROBUSTNESS_REPORT.md`).

| Defect | Faults | Fix | Regression guard |
|---|---|---|---|
| `/monthly-analysis` (`monthly_review.prepare`) skipped the intake gate entirely; a non-footing workbook ran to success with wrong numbers | F26 (SILENT-WRONG), F01, F12 | One gate, `close_artifacts.intake_gate`, used by `run_pipeline.py` and `prepare` before anything is written | `test_prepare_refuses_a_non_footing_workbook_and_writes_nothing`, G21 |
| pandas' default NA list turned 'n/a', 'NA', 'NaN' into silent blanks | F12, F18 | `read_excel(keep_default_na=False)`; text is recorded as a bad cell with its address; intake STOPs | `test_na_text_is_a_bad_cell_not_a_silent_blank`, G20 |
| Excel error values (#DIV/0!, #REF!) were read as blanks | F19 | Preflight lists error cells (openpyxl `data_type == "e"`) | `test_excel_error_value_stops` |
| '$1,234.56' and '(1,234.56)' became blanks | F14, F15 | `to_number()` normalises currency and parenthesised negatives | `test_money_text_and_bad_values`, `test_currency_text_is_read_as_the_same_number` |
| No footing check: a line could disagree with its section total | F26, F32 | Every section's lines must foot to its total in every month; gross and operating profit identities in every month, not only the latest | `test_line_that_does_not_foot_stops`, G21 |
| MoM was measured across a missing month (Jun vs Apr when May was absent) | F01, F02, F11 | Preflight STOPs when the target or prior month is missing; `build_computed` reports no MoM across a gap; margin-drop flags skip gaps | `test_no_mom_across_a_gap_and_prior_month_required`, `test_margin_flags_skip_a_gap`, G19 |
| Formulas saved without cached values read as blanks | F28 | Preflight STOPs and names the cells | G22 |
| Raw library errors instead of a cause (`KeyError`, `IndexError`, `BadZipFile`, `PermissionError`, "truth value of a Series is ambiguous") | F03, F24, F28–F31 | Preflight checks file, zip, sheets, header, merged and duplicate month headers, and required total rows first | `test_corrupt_and_locked_files_stop_with_a_cause`, `test_duplicate_month_raises_naming_both_cells` |
| No warning for an outlier ×1000, zero revenue, or a look-alike label | F16, F17, F23 | `run_client.cell_warnings`: outlier over 100× the median month (ABC's largest normal ratio is ~54×), zero revenue, non-ASCII labels | `test_outlier_and_lookalike_warnings_and_none_on_clean_data` |
| Found by the suite in this phase's own new code: the gap warning crashed on `Period` formatting | F02 | `strftime` | `test_gap_warning_names_the_month` |
| Found while writing the suite: the outlier screen took 9 s per call | — | Vectorised (0.06 s) | — |

## Workflow failure modes (2026-10-14, Phase 3: `04_architecture/workflows/`)

19 failure modes across workflows a–g were run by hand. Before the fixes, 10 failed badly: 8 tracebacks, 1 silent exit, and 1 overwrite of a saved file. 2 more surfaced raw library errors (`DateParseError`, `FileNotFoundError`). All now give one clear line; guarded by `tests/test_workflow_failures.py` (12 tests).
- **Path traversal:** `run_pipeline.py ../x 2026-06` built `outputs/../x/` before validating the id, and `client_sandbox` created `outputs/<client>/.tmp` for any id. Both now refuse invalid ids before building a path.
- **Tracebacks on the skill path:** `monthly_review.py prepare/build` crashed on refused intake, bad month, unknown client, or a missing or invalid packet, commentary or verdict. Now one `ERROR:` line naming the file and the next step.
- **Loader:** a bad `--from` and a missing or invalid `--compare` file crashed. An empty range exited 0 and **overwrote `outputs/abc/qbo_load_plan.json` with an empty plan** (found when the probe did exactly that; restored from git). Now a usage error, or a message with nothing written.
- **`approve.py`:** a damaged decision or verdict file crashed. Now it refuses, exits 5 and records nothing.
- **`qbo_test_connection.py`:** an invalid client id exited 2 with no output; `package_submission.py` crashed without git. The UI reported a timeout as "Could not start script".
- Not built: re-run as v2 after approval (a controls decision; see `04_architecture/workflows/c_approve_reject_lock.md`).

## Test leaked into real `outputs/` (2026-10-14)

- **Symptom:** an empty, untracked `outputs/nope/` appeared in the real outputs folder.
- **Cause:** `test_prepare_errors_are_one_line` ran `monthly_review.py prepare nope 2026-06` (and two `abc` failures) with no output root, so they used the real `outputs/`. `client_sandbox` creates `outputs/<client>/.tmp` before the unknown-client check and removed only `.tmp`, leaving `outputs/<client>/`. A mistyped client name by a real user would have left the same folder.
- **Fix:** `monthly_review.py prepare/build` take `--outputs-root` (default unchanged); the test passes a temp root and asserts both that the real `outputs/` listing is unchanged and that the temp root is empty after the failures. `client_sandbox` removes the empty client folder on exit. `test_build_names_the_missing_or_broken_input` now recreates its own `out/abc` folder rather than relying on the leftover one.
- **Check:** full unit suite run twice after deleting `outputs/nope/`: 129 OK both times, folder did not reappear. Golden 22/22.

## Fault-injection judge: six expectations ended stricter, none looser (2026-10-15)
The Balance Sheet tie-out (Current Year Earnings = year-to-date net income) was added after the fault declarations were fixed. Six faults declared WARN now hit that refusal first, so the run STOPs. `judge()` in `03_evals/robustness/fault_injection.py` accepts this only when the declared level is WARN, the run was refused (no packet, non-zero exit) and the message names the tie-out. The declarations themselves were not edited; the report marks these rows "stricter". Rule held: an expectation only moves WARN to STOP, never looser (HANDLE and STOP rows are judged exactly as before).

| Fault | Declared | Now | Why the tie-out stops it |
|---|---|---|---|
| F02 Sep 2025 column deleted | WARN | STOP | Year-to-date net income no longer reconciles to Current Year Earnings once a month is missing |
| F13 Blank Bonus cell, Feb 2026 | WARN | STOP | The blank changes net income; the Balance Sheet figure did not move |
| F16 Usage Fees x1000, Jun 2026 | WARN | STOP | Income Statement net income changed; Balance Sheet Current Year Earnings did not |
| F17 Zero revenue, Jun 2026 | WARN | STOP | Same: net income changed, Balance Sheet did not |
| F21 New account Crypto Mining Costs | WARN | STOP | Same: added cost changes net income, Balance Sheet did not |
| F27 Only 11 months supplied | WARN | STOP | Year-to-date net income no longer reconciles |

Cost, stated plainly: for these six the declared warning text (outlier, zero revenue, unmapped account, TTM withheld, gap) is no longer reached by the whole-run test, because the refusal comes first. That gap is closed by the F..b variants in the section below. Those warnings stay covered by the unit and golden tests, not by this suite.

## WARN-path coverage gap closed: six variants (2026-10-15, v3.0)
The six WARN declarations above only ever ran as STOP, so no run reached their warning path. Each now has a variant (F02b, F13b, F16b, F17b, F21b, F27b) that applies the same fault and restates the Balance Sheet (Current Year Earnings reset to the mutated year-to-date net income, Retained Earnings takes the opposite change; Total Equity, Total Liabilities and Equity and cash are untouched), so the tie-out passes. The originals are unchanged and still run as STOP (stricter than declared). Required behaviour, declared in `fault_injection.py` before the run: WARN on both entry points, with the expected text in `summary.json`, the review packet, the Data Quality sheet and the reviewer Excel's Open Questions (built by `monthly_review.build`), every detail-account amount other than the accounts the fault changes equal to the baseline, and cash equal to the baseline.

| Variant | Warning required | Result |
|---|---|---|
| F02b Sep 2025 column deleted | `Months missing from the source: Sep 2025` | WARN, pass |
| F13b Blank Bonus cell, Feb 2026 | `blank cell(s)` | WARN, pass |
| F16b Usage Fees x1000, Jun 2026 | `Possible outlier: Usage Fees` | WARN, pass |
| F17b Zero revenue, Jun 2026 | `Revenue is zero in Jun 2026` | WARN, pass after the fix below (first run: **FAIL**) |
| F21b New account Crypto Mining Costs | `Unmapped OPEX account ...: Crypto Mining Costs` | WARN, pass |
| F27b Only 11 months supplied | `TTM not available` | WARN, pass |

**Defect found by F17b:** with zero revenue the gross margin is None, and the reviewer pack crashed (`TypeError`) in two places, `owner_memo.render` ("you kept {gm:.1%} of revenue") and the Cover sheet in `monthly_review.build`. The run itself and its warning were fine, so the earlier STOP/WARN checks could not see it; only building the reviewer Excel did. Both now say the margin is not available. Regression guard: `test_owner_memo_survives_missing_gross_margin`. The expectation was not changed; the code was.
