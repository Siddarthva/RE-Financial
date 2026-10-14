# Fault suite against the code before Phase 2 (commit aedc2fa)

How: `03_evals/robustness/fault_injection.py` was run on 2026-10-14 in a temporary git worktree at `aedc2fa`. Only the skill path was run (`monthly_review.prepare`, step 1 of `/monthly-analysis`), because the old `run_pipeline.py` had no `--clients-root/--outputs-root` options. Kept by hand as evidence; the generated report is `ROBUSTNESS_REPORT.md`.

**Result: 9/32 as required. 8 SILENT-WRONG**: the run succeeded with wrong numbers and no warning.

| Outcome on old code | Faults |
|---|---|
| SILENT-WRONG | F12 'n/a' text, F13 blank cell, F14 '$1,234.56' text, F16 outlier ×1000, F17 zero revenue, F18 'NaN' text, F26 non-footing line. F15 '(1,234.56)' became blank, with only an indirect rollup warning |
| Only a weak or indirect warning where a STOP was required | F01 prior month missing, F11 merged header: MoM silently compared Jun with Apr; only "Months are not consecutive". F19 '#DIV/0!', F32 inf: only "Category rollup != total OPEX" |
| Ran where a STOP was required | F05 blank column inside the months |
| Stopped, but with a raw library error, not a message naming the cause | F03 "The truth value of a Series is ambiguous", F24 `KeyError: 'cost_of_goods_sold'`, F28 `IndexError: index -1 is out of bounds`, F29 "Excel file format cannot be determined", F30 `BadZipFile`, F31 `PermissionError: [Errno 13]` |
| Stopped with a usable pandas message, but no file or sheet list | F08, F09 "Worksheet named … not found" |
| As required | F04, F06, F07, F10, F20, F21, F22, F25, F27 |

The causes were:
- The skill path skipped the intake gate entirely.
- pandas' default NA list turned 'n/a' and 'NaN' into blanks.
- Excel error values were read as blanks.
- Currency text was not normalised.
- No footing check ran in any month.
- MoM was measured across missing months.
