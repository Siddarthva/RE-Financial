# 03_evals: evaluations

**Answers:** the brief's evaluation requirement. Show the numbers and commentary are right, and that the checks themselves can fail.

## Eval layers

| Layer | Command | What it proves | Latest (2026-10-14) |
|---|---|---|---|
| Unit tests | `python -m unittest discover -s tests` | Individual bugs stay fixed; client isolation; redaction; workflow failure messages | 129 run, 129 OK |
| Golden cases | `python 03_evals/run_golden_evals.py` | Engine numbers and flags equal values derived by hand from source cells | 22 / 22 |
| Commentary grader | `python 03_evals/grade_commentary.py` | Every number in the text matches the engine JSON; top-3 movements named; cash and runway covered | engine, reviewed and saved-skill text PASS; flawed control FAILs as intended |
| Mutation test | `python 03_evals/mutation_test.py` | The tests and golden cases above fail when a known bug is injected | 13 / 13 mutants caught (7 bug classes) |
| Robustness | `python 03_evals/robustness/fault_injection.py` | 32 corrupted workbooks each STOP, WARN or HANDLE as declared, on both entry points | 32 / 32; 0 silent wrong numbers |
| UI number checks | `python -m unittest tests.test_ui_numbers` | Every number the review UI displays exists in an engine JSON file; no page imports calculation code | 15 tests OK |

The 129 unit tests include the 15 UI tests, 14 robustness tests and 12 workflow-failure tests ([`tests/test_robustness.py`](../tests/test_robustness.py)). Run records: [`FINAL_RUN.md`](FINAL_RUN.md). Scoring rules in full: [`GRADING.md`](GRADING.md).

## Golden cases by source

[`golden_cases.json`](golden_cases.json) has 22 cases in three `source` groups. "Real workbook" means the ABC workbook read in memory, never modified.

| `source` | Count | IDs | What the group is |
|---|---|---|---|
| `workbook` | 4 | G01, G02, G03, G06 | Real data already triggers the rule; no cell changed |
| `workbook+perturbation` | 9 | G04, G05, G07, G08, G14, G19–G22 | One or two cells changed to trigger a rule (each case records the cell, original and new value, and purpose); G19–G22 write a perturbed copy to a temp file and require the intake gate to refuse it |
| ABC cell-sourced | 9 | G09–G13, G15–G18 | Expected values computed by hand from cached source cells (listed in each case's `source.cells`), not by the adapter |

| Case | Pins |
|---|---|
| G01–G03, G06 | MoM revenue, gross margin, TTM needs twelve consecutive months, expense category trend |
| G04, G05, G07, G08, G14 | Duplicate month rejected; missing revenue rejected; zero prior revenue gives a null %; short TTM history disclosed; month labels survive normalization |
| G09 | February is the peak marketing month in 2025 and 2026 |
| G10 | The 5 one-off items; Dec 2025 is the event month |
| G11 | Dec 2025 is the first valid TTM month; earlier months null for all five TTM metrics |
| G12 | Largest OPEX spike (Dec 2025 SBC) and largest recurring spike; % null when prior is 0 |
| G13 | Full Jun 2026 summary: values, MoM, margins, TTM |
| G15 | Platform Revenue step-down 45,000 → 26,666.66 (Jan 2026) |
| G16 | Bad Debts 12,935.29 in May 2026, reversing in Jun 2026 |
| G17 | Jun 2026 cash 713,481.26; runway 3.40 months (3-month window) |
| G18 | Gross margin falls over 5 pp: Mar 2025, Aug 2025, Apr 2026 only |
| G19–G22 | Intake STOP by family: structure, values, footing, coverage |

## How grading works

- **Tolerances:** currency ±0.005; ratios, percentages and margins ±0.000001; identity fields (account, month) exact. Score is passed / total, and below 100% fails.
- **Flags** (undefined %, % sign, TTM availability, one-offs, step change vs one-off, runway, spike vs reversal, validation) are pass/fail inside the golden cases. Table in [`GRADING.md`](GRADING.md#2-flags).
- **Commentary:** every number is extracted with its unit and must match an engine value within half a unit of the last digit shown (`$195.9k` matches 195,898.16). Years, small counts and day-of-month are skipped. The 3 largest line movements must be named; cash balance and "runway" with a months figure must appear. Direction words, causes and tone are **not** code-graded; they go to the reviewer and a human.
- **Mutation:** the runner refuses to start unless the unmodified copy is green. A mutant is caught if any unit test or golden case fails, and it is an eval gap if nothing does.
- **Robustness:** each fault declares STOP, WARN or HANDLE before it runs. A successful run with different numbers and no warning is SILENT-WRONG and always fails ([report](robustness/ROBUSTNESS_REPORT.md)).

## Regressions

A change is blocked by any of: a golden case that passed now fails; any unit test fails; a commentary number mismatch, a dropped top movement or lost cash coverage; a flag that changes behaviour; the source workbook's bytes changing; a caught mutant that now survives; a client-isolation failure; a new data-quality warning that no one reviewed; any fault that stops behaving as declared or any SILENT-WRONG. Full list of nine: [`GRADING.md`](GRADING.md#6-what-counts-as-a-regression). Wording changes that keep every number and movement are not regressions.

### Before any commit

Run in this order from the repo root (PowerShell, except the secret scan, which is Git Bash). Skip mutation and robustness only if you changed nothing under `src/`, `scripts/` or `clients/`.

```powershell
python -m unittest discover -s tests                                                          # expect OK (129)
python 03_evals/run_golden_evals.py                                                           # expect Score: 22/22
python 03_evals/grade_commentary.py                                                           # engine text: PASS
python 03_evals/grade_commentary.py --commentary outputs/abc/commentary_2026-06.md            # reviewed text: PASS
python 03_evals/grade_commentary.py --commentary outputs/skill_commentary.md                  # saved skill output: PASS
python 03_evals/mutation_test.py                                                              # expect 13/13 caught, ~6 min
python 03_evals/robustness/fault_injection.py                                                 # expect 32/32, ~3 min
python scripts/check_links.py                                                                 # expect 0 broken links
(Get-FileHash "data/ABC Inc - Financial Statements.xlsx").Hash                                # expect 75DA8D679A89551F…
```

```bash
git ls-files -z | xargs -0 python scripts/scan_secrets.py                                     # expect 0 findings
```

## What the evals caught

Defects 1–16, plus the robustness and workflow fixes of Phases 1–3, with fixes and regression tests, are in [`evals_caught.md`](evals_caught.md). The five that matter most:

| # | Story | Found by | Link |
|---|---|---|---|
| 1 | The `/monthly-analysis` path skipped the intake gate: a workbook whose subtotal did not foot (+1,000 on one line) ran to success with wrong numbers. The suite scored 9/32 with 8 SILENT-WRONG before the fix, 32/32 after. | Fault injection | [`BEFORE_FIX.md`](robustness/BEFORE_FIX.md), [`ROBUSTNESS_REPORT.md`](robustness/ROBUSTNESS_REPORT.md) |
| 2 | Shifting every month forward by one survived the first mutation run (9 of 10 caught): every test checked relative values only. Golden case G14 was added to pin values to their months. | Mutation test | [`evals_caught.md`](evals_caught.md) |
| 3 | The grader failed the engine's own commentary (0/3 movements, no cash) and the saved skill text, which still said runway "cannot be calculated" while the engine computed it. The grader was left alone; the text was fixed. | Commentary grader | [`FINAL_RUN.md`](FINAL_RUN.md), [`evals_caught.md`](evals_caught.md) |
| 4 | MoM % had the wrong sign when the prior value was negative, so a shrinking loss printed as a negative change (`+8,343.52 (-2.5%)`). Fixed by dividing by `abs(prior)`; null when the prior is 0. | Source-cell reconciliation, G12 | [`evals_caught.md`](evals_caught.md) |
| 5 | `scan_secrets.py` given file paths scanned 0 files and reported 0 findings, a false clean. A misspelt path also passed. | Clean-state re-verification | [`verification_matrix.md`](../04_architecture/verification_matrix.md) |

## Add a golden case

1. **Choose the claim** the engine must get right, and find the source cells (sheet, cell addresses) that prove it. Income Statement columns run newest first (C = Jun 2026 … T = Jan 2025); Balance Sheet is one column to the right.
2. **Derive the expected value by hand** from cached cell values, in plain Python or a calculator, not from the engine. Record each cell in `source.cells`.
3. **Add the case** to [`golden_cases.json`](golden_cases.json) with the next free ID, a `source` of `workbook`, `workbook+perturbation` or a cell-sourced `source` object, and an `expected` block. For a perturbation, record sheet, cell, original and new value.
4. **Wire it** into [`run_golden_evals.py`](run_golden_evals.py) if it needs a new check type. Run it and confirm it passes, then break the engine on purpose and confirm it fails.
5. **Update counts everywhere**, then run `python scripts/check_links.py` and the sequence above.

Never edit an expected value to make a case pass. If one looks wrong, show the source-cell evidence and ask first ([`CLAUDE.md`](../CLAUDE.md)).
