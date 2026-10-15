# Final cold review (independent subagent, candidate v3.0-submission)

A fresh subagent that had not seen the work was given only the brief's text and the unzipped package, and asked to act as a skeptical senior engineer with 30 minutes. This is its report, lightly condensed. The "Fixed after review" section at the end lists what was changed in response; nothing else was edited.

## a) Deliverables and opens from root
All four were found in 2 opens from the root README: connection `01_connection/connection_decision.md`; skill `.claude/skills/monthly-financial-analysis/SKILL.md` (hidden folder, explained at README section 2); evals `03_evals/GRADING.md`; architecture `04_architecture/architecture.md` (PDF confirmed one page).

## b) Scores (before fixes)
| Criterion | Score | Main evidence / weakness |
|---|---|---|
| 1. Connection choice + team hosting | 4 | Scored options, "what would change my mind", phased hosting design. Weak: README called the native connector "Rejected" while the decision doc says only "unverified"; hosting is a design only; npm audit findings unfixed. |
| 2. Credential and data handling | 5 | Lifecycle table, threat table with residual risks, tested redaction and guard hook, scan found only fake canaries. |
| 3. Maintainable skill | 4 | Authoring kit, config reference, second client from config alone. Weak: much more than the brief asked for; trigger evals only structure-checked. |
| 4. Evals tell better from worse | 4 | Cell-sourced golden cases, mutants, faults, a flawed control that must fail. Weak: grader checks numbers/movements/coverage, not tone; mutants and faults are author-chosen. |
| 5. Clear, honest communication | 3 | Honest "not done" section. Penalised for stale counts in the root README and one PDF. |

Biggest weakness: QuickBooks data is not an input to the analysis. The sandbox returns only Intuit's sample company; the skill reads the supplied workbook; the loader that would bridge them was never applied. This is stated honestly in the README and overview PDF.

## c) Stale, contradictory or unverifiable claims found
- Root README: "Golden cases (22)", golden-source table totalling 22, "Mutation test (13)", "Fault injection (32)", "9 of 32 faults", mutation test "about 15 minutes" vs "~6 min" elsewhere.
- Evals PDF robustness matrix totalled 32 (16/8/8) beside a 38/38 headline.
- README said results were from 2026-10-14 clean-state runs; the counts are from 2026-10-15.
- `00_START_HERE/README.md` gave the verification PDF as 8 pages; it has 9.
- README repository map listed a non-existent `config/` folder; the root README named two clients while `clients/` holds three.
- README called the native connector "Rejected" with reasons the decision doc does not claim.
- `outputs/golden_run.txt` and `outputs/eval_results.json` were stale generated files (22/22).
- `verification_matrix.md` mixes labelled Phase 1 counts with current counts (labelled, but easy to misread).
- Unverifiable from files alone: live QuickBooks results (the MCP server clone is untracked), the "4 minutes" G18 rehearsal, the author-run falsification review, and the Intuit token lifetimes (marked "not re-checked" in the decision doc).

## d) Number traces (all matched the workbook)
| Commentary | Source | Result |
|---|---|---|
| Revenue 195,898.16, down 12,452.80 | Income Statement C14 / D14 (208,350.96) | Match |
| Cash 713,481.26, down 215,543.33 | Balance Sheet D15 and May column (929,024.59) | Match |
| Bad Debts −1,806.24 from 12,935.29 | Income Statement C31 / D31 | Match |

## e) Verdict (before fixes)
Advance, with reservations. Parts 1 and 3 are stronger than the usual take-home, evals demonstrably fail when they should, and the author separates Implemented / Proposed / Not done. Reservations: (1) the connected data is not the analysis input; (2) scope creep and documentation drift, with the first README still carrying old counts; (3) team hosting is a design only. Final-round probes it would use: why the QuickBooks data was not fed into the analysis, how to simplify for a teammate, how to test LLM-written commentary beyond number matching.

## Fixed after review
Stale counts and dates in the root README, the Evals PDF source, `verification_matrix.md` and `00_START_HERE/README.md`; the non-existent `config/` map entry; the three-client wording; the native-connector wording (now "Not chosen (unverified, not shown worse)"); an "In brief" block at the top of both READMEs; stale `outputs/golden_run.txt` and `eval_results.json` regenerated. Not fixed (stated in README section 17): no live QuickBooks data in the analysis, hosting as design only, author-chosen mutants and faults, tone not machine-graded.
