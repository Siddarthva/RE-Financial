# Final run record

Machine: Windows 11, Python 3.13.5, run from `ai_solutions_builder_free/`. Times are local (UTC+05:30), 2026-10-13.
Source workbook SHA-256 `75da8d679a89551f…` was identical before and after every run.

## Commands

```
python -m unittest discover -s tests
python evals/run_golden_evals.py
python evals/mutation_test.py
python evals/grade_commentary.py                                                   # engine's own commentary
python evals/grade_commentary.py --commentary ../outputs/abc/commentary_2026-06.md # reviewed commentary (from /monthly-analysis)
python evals/grade_commentary.py --commentary ../outputs/skill_commentary.md       # saved skill output
python src/run_client.py abc
python src/run_client.py xyz
python scripts/scan_secrets.py . ../outputs
```

## Result: v1.2-ui run (adds the workspace UI), 2026-10-14

Windows 11, Python 3.13.5, Streamlit 1.65.0. Source workbook SHA-256 `75da8d679a89551f…` was identical before and after. Commands as above, plus `python -m unittest tests.test_ui_numbers` (part of `discover`). The first attempt of the new UI test failed on three of my own test assumptions (numpy loaded by pandas, 2-decimal percentages printed by the commentary, global eval JSON not in the allowed set); fixed in the test, no app change was needed for those. The secret scan then flagged the test's deliberate fake canaries (5 findings), fixed by declaring the file a fake-fixture file as the other fixture files do.

| Check | Result | Counts |
|---|---|---|
| Unit tests | **PASS** | 90 run, 90 OK (75 before + 15 in `tests/test_ui_numbers.py`) |
| Golden cases | **PASS** | 17/17 |
| Mutation test | **PASS** | 13 mutants, 13 caught, 0 survived (UI tests skip inside the mutant copies: no `app/` there) |
| Commentary: engine's own text | **PASS** | numbers 28/28; top movements 3/3; cash risk covered |
| Commentary: reviewed text (`outputs/abc/commentary_2026-06.md`) | **PASS** | numbers 27/27; top movements 3/3; cash risk covered |
| Commentary: saved skill output (`outputs/skill_commentary.md`) | **PASS** | numbers 36/36; top movements 3/3; cash risk covered |
| Client `abc` | **PASS** | 18 months, Jan 2025-Jun 2026, 0 warnings |
| Client `xyz` | **PASS** | 14 months, Apr 2025-May 2026, 1 expected warning |
| Secret scan | **PASS** | 0 findings in 231 text files (project incl. `submission/`, `../outputs`, `../app`); 0 secret-named files; 7 declared fake-fixture files skipped |

What `tests/test_ui_numbers.py` proves: every page renders for abc and xyz with no exception; every $ / % / pp shown exists in that client's engine JSON; key Overview figures, the revenue-by-stream table, TTM "not available" before Dec 2025, and the flux sort order equal the engine values; no page imports a calculation module (static scan plus a clean interpreter); fake tokens / realm IDs planted in `qbo_status.json` are withheld; empty states render with no outputs; an approved period renders as locked. Fault injection: a 1% change to a displayed revenue and an import of `financial_analysis` in a page were each caught (7 failures, 2 errors), then reverted.

Not covered / caveats:
- The Approve, Reject, Run analysis, Run golden evals (from the UI) and Test connection buttons are not exercised by the suite (approve would lock a real period; test-connection calls QuickBooks). Run golden evals was clicked once by hand.
- Row-click evidence panels (flux, golden cases) need a browser; AppTest cannot select dataframe rows.
- The skill was still not re-run live; the reviewed and saved-skill rows grade files on disk, as before.
- `docs/workflow.md` and `docs/brief_traceability.md` do not exist; their tabs show an empty state.

## Superseded by the v1.2-ui run above: the final run before the UI (fourth attempt, clean re-run), 04:48:22 – about 04:52

Source workbook SHA-256 `75da8d679a89551f…` was identical before and after.

| Check | Result | Counts |
|---|---|---|
| Unit tests | **PASS** | 75 run, 75 OK |
| Golden cases | **PASS** | 17/17 |
| Mutation test | **PASS** | 13 mutants, 13 caught, 0 survived |
| Commentary: engine's own text | **PASS** | numbers 28/28; top movements 3/3; cash risk covered |
| Commentary: reviewed text (`outputs/abc/commentary_2026-06.md`) | **PASS** | numbers 27/27; top movements 3/3; cash risk covered |
| Commentary: saved skill output (`outputs/skill_commentary.md`) | **PASS** | numbers 36/36; top movements 3/3; cash risk covered |
| Client `abc` | **PASS** | 18 months, Jan 2025–Jun 2026, 0 warnings |
| Client `xyz` | **PASS** | 14 months, Apr 2025–May 2026, 1 expected warning (no Sales & Marketing accounts, reported as not available) |
| Secret scan | **PASS** | 0 findings in 195 text files (project incl. `submission/`, plus `../outputs`); 0 secret-named files; 6 declared fake-fixture files skipped |

Overall: **everything passes.** Both commentary gaps recorded in the third attempt are closed: the engine's `generate_commentary()` now names the top movements and cash, and the saved skill output now covers cash and runway.

Caveats:
- The skill was **not** re-run live in this run. The third row grades the saved file as it stands on disk, not a fresh `/monthly-analysis` generation.
- The reviewed-text row grades `outputs/abc/commentary_2026-06.md`, which existed before this run.
- The "engine's own text" grade runs against the output of the engine as changed since attempt 3 (commit-free folder, no diff history to show what changed).

## Previous "final run" (third attempt, 04:22:54 – 04:25:19), superseded

Unit 74/74, golden 17/17, mutation 13/13, both clients PASS, secret scan PASS (0 findings in 105 files). The engine's own commentary **FAILED** (numbers 15/15, top movements 0/3, cash risk not covered) and the saved skill output **FAILED** (numbers 43/43, 3/3, cash risk not covered). It was followed by a comment-only edit to `tests/test_scan_secrets.py` and a unit re-run (74 passed).

## Earlier attempts the same day (failures kept on record)

| Attempt | Time | Unit | Golden | Mutation | What failed |
|---|---|---|---|---|---|
| 1 | 04:19:17 | 69 / 69 | 17/17 | **FAIL, did not run** (exit 2) | Baseline copy was not green: `tests/test_qbo_load.py` imports `scripts/`, which the mutation runner did not copy. |
| 2 | 04:21:49 | 73 / 73 | 17/17 | **FAIL, did not run** (exit 2) | After `scripts/` was copied, the three `test_qbo_load` classes errored: in a copy with no `outputs/` folder, `client_sandbox` blocked its own `mkdir`. This also would have broken a reviewer's first `run_client.py`. |
| 3 | 04:22:54 | 74 / 74 | 17/17 | 13/13 caught | Mutation passed; two commentary checks failed (known gaps, since closed). |
| 4 | 04:48:22 | 75 / 75 | 17/17 | 13/13 caught | Nothing failed. Final run above. |

Both fixes are logged in `docs/evals_caught.md` (#12, #14) with a regression test for #14. The secret scan also found one realistic-looking fake realm ID in a test fixture (#13), replaced before the final run.

## Secret scan details

`scripts/scan_secrets.py` checks for JWTs, Intuit-style tokens, bearer headers, realm IDs, `*_secret`/`*_token`/`api_key`/`password` assignments with real-looking values, auth codes in URLs, private keys and email addresses. Placeholders and `process.env` references are ignored; the output never contains a matched value. Files named `.env`, `*token*` or `*credential*` are listed by name only and never opened.

- `ai_solutions_builder_free/` (including `submission/`) and `outputs/`: 0 findings. Fake fixtures declared: `tests/test_evidence_redaction.py`, `tests/test_scan_secrets.py`, and the scanner itself (each also in `submission/`).
- The upstream `quickbooks-online-mcp-server/` clone, scanned separately and **not** part of the submission: 28 hits, all code that mentions variables such as `refresh_token`, plus one example realm ID in its `docs/TESTING.md`. I did not read each one. It has a `.env` (listed by name, never opened) that holds the sandbox credentials and must stay out of any shared copy.

## Audit-gap fixes, 2026-10-13

| # | Item | Status |
|---|---|---|
| 1 | `.mcp.json.example` (stdio, 3 DISABLE flags = true, env var names only); linked from `SETUP.md`, `connection_decision.md` | Done |
| 2 | `part1-quickbooks-mcp.md` now cites the 8 redacted pairs (captured 2026-10-12, re-run 2026-10-13) | Done |
| 3 | `architecture.md` Memory section added (33 lines, still one page) | Done |
| 4 | Skill, command, agent: no "runway cannot be calculated" text; `submission/` copies identical to source; no stale paths | Verified |
| 5 | Golden source cell ref: 8 of 17 have `source` (G09-G13, G15-G17); G01-G08, G14 do not (synthetic inputs, no workbook cell) | Gap, listed |
| - | Unit tests 75/75, golden 17/17 re-run; `submission/` in sync | Pass |
