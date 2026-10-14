# Grading

There are four graders. Each is pass/fail and must be green before a change is called done.

| Grader | Command | Checks |
|---|---|---|
| Golden cases | `python 03_evals\run_golden_evals.py` | Numbers and flags produced by the engine (`src/`) |
| Commentary | `python 03_evals\grade_commentary.py [--commentary FILE \| --run-skill]` | Every number in written commentary, coverage of the top movements, and the cash risk |
| Mutation | `python 03_evals\mutation_test.py` | That the two graders above actually catch known bug classes |
| Robustness | `python 03_evals\robustness\fault_injection.py` | 32 corrupted copies of the workbook: each must STOP, WARN or be HANDLED as declared, on both entry points (`run_pipeline.py` and the `/monthly-analysis` prepare step); never a successful run with wrong numbers and no warning |

Unit tests (`python -m unittest discover -s tests`) guard individual bugs; see `03_evals/evals_caught.md`.

## 1. Numbers (golden cases)

`03_evals/golden_cases.json` has 22 cases in three `source` groups: `workbook` 4 (G01, G02, G03, G06), `workbook+perturbation` 9 (G04, G05, G07, G08, G14, G19–G22) and ABC cell-sourced 9 (G09–G13, G15–G18). They fall into three kinds:

- **G01–G08 and G14, real workbook (in memory, never modified):** the same engine rules as before (MoM, margin, TTM eligibility, validation errors, month labels kept intact), now fed from cached Income Statement cells. Each case records `source`, `perturbation.cells_changed` (sheet, cell, label, original, new) and a one-line `perturbation.purpose`. The runner refuses a case whose recorded original differs from the workbook. Expected values were computed in plain Python from the source cells, not from the engine.
  - `workbook+perturbation` (G04, G05, G07, G08, G14): one or two cells changed to trigger the rule. Where a changed cell is a formula (G07, T14), its cached value is overridden directly.
  - `workbook` (G01, G02, G03, G06): real data already triggers the rule, so no cell is changed.
  - None remain synthetic.
- **G19–G22, intake gate:** a perturbed values-only copy is written to a temp file; `close_artifacts.intake_gate` must refuse it, and its message must contain every `expected.message_contains` string. Recorded originals are checked against the workbook, as for G04 and the other perturbation cases.
- **G09–G13 and G15–G18, real ABC workbook:** expected values were computed by hand from cached source-cell values, not from the adapter. Each case's `source.cells` gives the cells or `SUM` ranges used. Both sheets run newest first: on the Income Statement, column C = Jun 2026 … column T = Jan 2025; on the Balance Sheet, column D = 30 Jun 2026 … column U = 31 Jan 2025 (one column to the right).

| Case | What it pins | Key source cells |
|---|---|---|
| G09 | February is the peak marketing month in both 2025 and 2026 (the only repeating peak; no revenue seasonality is asserted) | S71, G71, S65, G65 |
| G10 | The 5 one-off items; Dec 2025 is the event month | T86, N93, I101, I99, E13, I103, I107 |
| G11 | Dec 2025 is the first valid TTM month; TTM is null for every earlier month (Jan–Nov 2025) and every metric | SUM(I14:T14) etc. |
| G12 | Largest OPEX spike overall and among recurring categories; % change is null when the prior is 0 | I99−J99, S65−T65 |
| G13 | Full Jun 2026 summary: values, MoM, margins, TTM | C14…C107, SUM(C:N) |
| G15 | Platform Revenue steps down 45,000 → 26,666.66 in Jan 2026 (−18,333.34, −40.7%) and holds through Jun 2026 | I8, H8, C8:H8 |
| G16 | Bad Debts 12,935.29 in May 2026 (% change null: prior 0), reversing to −1,806.24 in Jun 2026 | E31, D31, C31 |
| G17 | Jun 2026 cash 713,481.26 and runway: 3.40 months at the 3-month average cash decline (1- and 6-month: 3.31, 2.29) | BS D15, E15, G15, J15 |
| G19–G22 | Intake gate STOP, one per fault family (perturbed values-only copy in a temp file): G19 structure, prior month's header blanked (D5); G20 values, 'n/a' in C11; G21 footing, F11 +1,000 with F14 unchanged; G22 coverage, formulas saved without cached values | D5, C11, F11/F14, all 144 formula cells |
| G18 | Gross margin falls by more than 5 pp (config `thresholds.gross_margin_drop_pp`) flag exactly Mar 2025 (−8.10 pp), Aug 2025 (−7.30 pp) and Apr 2026 (−5.36 pp) | R/S, M/N, E/F rows 14 and 26 |

**Tolerances:** currency within ±0.005 (one half-cent). Ratios, percentages and margins within ±0.000001. Identity fields (account, month, peak month) must match exactly.

**Score:** passed / total. Anything below 100% fails.

## 2. Flags

A flag is a qualitative judgment the engine must get right, apart from the arithmetic. Flags are scored as exact pass/fail inside the golden cases:

| Flag | Correct behaviour | Case |
|---|---|---|
| Undefined % change | Prior value = 0 gives `null`/N/A, never ±infinity or a made-up % | G07, G12 |
| % sign | % change has the same sign as the $ change (divide by \|prior\|), including negative bases | G13 (net income), unit tests bug1/bug5 |
| TTM availability | TTM is null until 12 consecutive calendar months exist; a short history is disclosed | G03, G08, G11 |
| One-off items | Detail row non-zero in exactly one month and \|amount\| ≥ 5,000 | G10 |
| Event month / non-recurring | Dec 2025 is the only month with positive net income (+534,551.41). It is driven by two non-recurring items: Income Tax Benefit −1,244,429.84 (I101) and Stock-Based Compensation 334,660.53 (I99). Adjusted NI excluding them = −375,217.90 | G10 |
| Step change vs one-off | A new level that persists (Platform Revenue from Jan 2026) is a step change, not a one-off | G15 |
| Runway | Burn = average monthly decline in Balance Sheet cash, never net income; no runway when cash did not fall | G17, unit test |
| Spike vs reversal | A spike is an increase to a positive expense. A credit reversing to zero (Income Tax Benefit, Jan 2026) is not a spike | G12 |
| Validation | Duplicate months and missing revenue are rejected with a clear error | G04, G05 |

## 3. Commentary

`grade_commentary.py` rebuilds the **computed JSON** from the engine on the real workbook and writes it to `outputs/abc_computed.json`. It then grades the commentary text:

- **Default:** the adapter's `generate_commentary()`.
- **`--commentary FILE`:** any saved text.
- **`--run-skill`:** runs the `monthly-financial-analysis` skill headless via `claude -p` and saves its text to `outputs/skill_commentary.md`.

The computed JSON contains:
- every month's totals (value, MoM $ and %, TTM), margins, margin change in pp, and TTM margins;
- the latest month's line items: value, prior value, MoM $ and %, and share of OPEX;
- `cash`: latest Balance Sheet cash, prior cash, MoM $ and %, average monthly burn and runway in months for 1-, 3- and 6-month windows (3-month is primary).

**Number extraction.** Every number in the text is extracted with its unit (`$`, `%`, `pp`/percentage points, `k`/`M`).

- **Skipped as non-claims:** years 2000–2100, unitless integers below 100 (counts such as "12 months", "3 questions", list markers), and day-of-month after a month name.
- **Everything else is a claim.**

**Number matching.** A claim matches if a computed value of the same unit lies within half a unit of the last decimal place shown. For example:
- "$195.9k" matches 195,898.16 (±50);
- "6.0%" matches 5.9768% (±0.05);
- "$12,452.80" must match to ±0.005.

Only the magnitude is compared. Direction words ("down", "fell") are checked by the reviewer, not the grader.

**Top movements.** The 3 largest absolute MoM $ changes in the latest month, ranked across *all* detail rows (revenue streams, COGS, OPEX), must each be named. A name counts if the full account label appears, or the part after the last ":" (e.g. "Partner Marketing"). For Jun 2026 these are:
- Events & Conferences +17,970.67 (C65−D65)
- Bad Debts −14,741.53 (C31−D31)
- Usage Fees −11,142.74 (C11−D11)

**Cash risk.** The commentary must (a) state the cash balance (a number matching 713,481.26 within its displayed rounding, e.g. "$713.5k") and (b) use the word "runway" with a figure in months that matches one of the computed runway values within its rounding ("about 3 months", "3.4 months" and "2.3 months" all match; "5 months" does not). Runway figures are read by a separate pattern because whole numbers below 100 are otherwise skipped.

**Score:** pass only if all extracted numbers match, at least one number was found, all 3 movements are named, and the cash risk is covered. The report shows numbers matched/checked and movements mentioned/3; the detail goes to `outputs/commentary_grade.json`.

**Known limits:**
- A number can match a coincidentally equal value for a different metric, because matching is by value, not by metric.
- Causal language and narrative quality are not scored automatically. They stay with the human reviewer, under the skill's commentary rules.

## 4. Mutation testing

`03_evals/mutation_test.py` copies `src/`, `tests/`, `03_evals/` and the workbook into a temporary folder and injects one bug at a time into each engine module. It then runs the unit tests and golden cases against that copy. The original files are never modified. Bugs injected: reversed month order (in the adapter, newest-first columns labelled as if oldest first), flipped revenue sign, subtotals (Total S & M Payroll, Total Marketing) summed with their detail rows, months shifted by one, one opex category dropped, TTM over 11 months, and gross margin divided by COGS instead of revenue. The report lists every failing test and golden case for each mutant.

- **Caught:** at least one unit test or golden case fails.
- **Survived:** nothing fails. That's an eval gap: add a case that fails for that mutant, then re-run.
- The runner refuses to start unless the unmodified copy is fully green. A mutant whose original text no longer exists in the code is an error, not a pass.

The report goes to `outputs/mutation_report.md`.

## 5. Robustness (fault injection)

`03_evals/robustness/fault_injection.py` writes a corrupted COPY of the workbook into a temp folder for each of 32 faults: structure, values, labels and coverage. It never touches `data/` or `outputs/<client>/`, and it checks the source SHA-256 before and after. It then runs both entry points that produce numbers on that copy: `scripts/run_pipeline.py --clients-root/--outputs-root` and `monthly_review.prepare`. The required behaviour is declared per fault before it runs:

- **STOP:** intake refuses with a message naming the cell, sheet or cause, and no review packet is written.
- **WARN:** the run continues, and the warning appears in the review packet (Open Questions in the sign-off pack) and in the analysis workbook's Data Quality sheet.
- **HANDLE:** no new warning, and every review-packet number and every account amount equals the baseline.

A successful run with different numbers and no warning is **SILENT-WRONG** and always fails. The report is `03_evals/robustness/ROBUSTNESS_REPORT.md` (generated) and `outputs/robustness_results.json`. The same suite against the pre-fix code scored 9/32 with 8 SILENT-WRONG (`03_evals/robustness/BEFORE_FIX.md`). Fast unit-level guards for each fix are in `tests/test_robustness.py`. G19–G22 pin one STOP per family.

## 6. What counts as a regression

Any of the following is a regression and blocks the change:

1. Any golden case that passed now fails, or the golden score drops below 100%.
2. Any unit test fails.
3. Commentary grading of the engine or the skill shows a number that doesn't match, misses a top movement it previously named, or drops the cash risk after covering it.
4. A flag changes behaviour, e.g. a null % becomes a number or infinity, TTM appears for a non-consecutive window, a one-off disappears or a new one appears, or a % sign stops following its $ change.
5. The source workbook's bytes change after a run (check its SHA-256).
6. Any mutant that was caught now survives `mutation_test.py`.
7. Any client-isolation test fails (`tests/test_client_isolation.py`): a run reading another client's folder or outputs, or writing outside `outputs/<client>/`.
8. A client config change produces a data-quality warning that wasn't there before, unless the change was intended and reviewed.
9. Any fault in `fault_injection.py` stops behaving as required on either entry point, or any SILENT-WRONG appears (run it after any change to `src/`, `scripts/run_pipeline.py` or a client config).

**Not a regression:**
- Wording changes in commentary that keep every number matching and every top movement named.
- New golden cases or new tests.

**Changing expected values.** Never edit an expected value to make a case pass. If an expected value seems wrong, show the source-cell evidence and get approval first (see the root `CLAUDE.md`). The cell references in `source.cells` exist to make that check quick.

## Baseline (2026-10-12)

- Golden cases: 14/14.
- Unit tests: 34/34 (13 added for per-client config and isolation).
- Mutation testing: 10/10 caught. The first run had 1 survivor (months shifted in `normalize_monthly`), closed by G14.
- Engine `generate_commentary()`: 15/15 numbers, **0/3 movements → FAIL.** Known gap: the engine's rule-based commentary names only totals.
- Skill run 1 (before the skill named top movements across all lines): 53/53 numbers, 2/3 movements → FAIL (Usage Fees missing). Saved in `outputs/skill_commentary_run1.md`.
- Skill run 2 (after the skill guidance fix): 43/43 numbers, 3/3 movements → **PASS.** Saved in `outputs/skill_commentary.md`.

## Current baseline (2026-10-13)

- Golden cases: **17/17 PASS** (G15–G17 added; G11 now checks every earlier month is null).
- Unit tests: **75/75 PASS** (clean re-run 2026-10-13).
- Mutation testing: **13/13 caught** (reverse month order ×2 and sum subtotals twice added). Thin spots: the double-counted subtotals are caught only by unit tests, not by a golden case, and the adapter's wrong margin denominator only by G13. `evidence/` is now copied into the throwaway project, so the runner's baseline is green again.
- Reference commentary `outputs/reference_commentary_jun2026.md` (positive control): 13/13 numbers, 3/3 movements, cash risk covered → **PASS**.
- Engine `generate_commentary()`, reviewed text and saved skill output (`outputs/skill_commentary.md`): all **PASS** as of the 2026-10-13 clean re-run (28/28, 27/27 and 36/36 numbers; 3/3 movements; cash risk covered). The earlier FAILs for the engine text and the saved skill output are kept in `03_evals/FINAL_RUN.md`. The skill output was graded as saved, not regenerated live.

The latest full run, with commands, counts and the failures along the way, is in `03_evals/FINAL_RUN.md` (unit tests 75/75, golden 17/17, mutation 13/13).
