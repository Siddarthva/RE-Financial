# Live consistency check: `/monthly-analysis abc 2026-06`, 3 headless runs

**Question:** when the same slash command is run live several times, does the wording vary while the graded facts stay put?
**Answer:** yes. No two runs share a single statement word for word, but all three runs pass the grader on the same facts.

## Setup

- Command: `claude -p "/monthly-analysis abc 2026-06" --model sonnet`, one fresh session per run, each into its own temp output folder (`--outputs-root`).
- Grader: `python 03_evals/grade_commentary.py --commentary <run>/abc/commentary_2026-06.md`. The grader and the expected values were not changed.
- Reviewer verdict: the `finance-reviewer` subagent's final saved `review_2026-06.json`.
- Run date: 2026-10-14 (file named for 2026-10-15 as requested).

## Results

| Run | Numbers matched | Top-3 named | Cash / runway | Reviewer verdict | Word count |
|---|---|---|---|---|---|
| 1 | 32 / 32 | 3 / 3 | cash stated, runway stated | approve (0 changes) | 218 |
| 2 | 37 / 37 | 3 / 3 | cash stated, runway stated | approve (0 changes) | 207 |
| 3 | 28 / 28 | 3 / 3 | cash stated, runway stated | approve (0 changes) | 210 |

Grader result: **PASS** on all three. Word count is the whole commentary file. The number of statements was 12, 14 and 12.

## What was identical in all three runs

These facts appear in every run. Only the sentence around them changes.

| Fact | Value |
|---|---|
| Revenue 2026-06 | 195,898.16, down 12,452.80 (5.98%) from 208,350.96 |
| Gross profit 2026-06 | 137,425.72, down 2,255.71 (1.61%) |
| Gross margin | 70.15%, up 3.11 percentage points |
| Operating expenses 2026-06 | 468,181.80, down 10,599.23 (2.21%) |
| Net income 2026-06 | -330,756.08, an improvement of 8,343.52 from -339,099.60 |
| Net margin | -168.84%, a 6.09 percentage-point fall |
| Top 3 movements, in this order | Events & Conferences +17,970.67; Bad Debts -14,741.53 (12,935.29 to -1,806.24); Usage Fees -11,142.74 |
| TTM to 2026-06 | revenue 2,303,975.51; net income -3,089,779.59 (TTM gross margin 69.46% is in runs 1 and 3 only) |
| Cash 2026-06 | 713,481.26, down 215,543.33 from 929,024.59 |
| Runway | 3.4 months on the 3-month window, burn 209,656.62, "past balances only, not a forecast" |
| Data-quality warnings / one-offs | stated (the packet has none) |
| Reviewer open questions | 4 in each run |

## What varied between runs

| Aspect | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| Statements verbatim in another run | 0 | 0 | 0 |
| Direction wording | "down", "an improvement of" | "a decrease of", "an improvement of" | "a change of -12,452.80", "+8,343.52" |
| Percent sign | "(-5.98%)", "(-1.61%)" | unsigned "(5.98%)", "(1.61%)" | signed "(-5.98%)", "(+2.46%)" |
| Extra facts added beyond the shared set | TTM gross profit 1,600,427.91, TTM gross margin 69.46%, TTM net margin -134.11% | Prior-month values: gross profit 139,681.43, operating expenses 478,781.03, gross margin 67.04%, net margin -162.75%; the Events & Conferences and Usage Fees balances (29,294.58 from 11,323.91; 166,781.50 from 177,924.24) | TTM gross margin 69.46%; net income change +2.46%; Bad Debts "(a credit)" |
| Statement count | 12 | 14 | 12 |

Every extra fact was matched by the grader against the engine JSON. The variation is in phrasing and in how many extra, correct facts a run adds, not in the facts it must state.

## Caveats

- **Run 3 took three attempts.** Three earlier attempts at the third run stopped at the revise step with a permission denial on writing the revised commentary and the review JSON (no commentary was graded from them): one in the scratchpad folder, one again in the scratchpad folder, one in `outputs/_live_tmp/`. The attempt that is reported ran with `--permission-mode acceptEdits`, which you approved for this run. Runs 1 and 2 did not use that flag. The denials were a permission block, not wrong output, but this is a replaced sample, not a clean first draw.
- **Run 3 did not run `build`.** Its report says the Excel pack was not built, so run 3 has a commentary and review but no `monthly_review_2026-06.xlsx`. Runs 1 and 2 built the pack. The grade and verdict above do not depend on it.
- **Run 3 review file.** The saved reviewer JSON contains `&amp;` in "Events &amp; Conferences". It was saved as returned and has no effect on the verdict.
- Three runs show consistency on one client-month. They don't bound the variation across many runs, and they say nothing about months with warnings or one-offs.
- The temp output folders were not kept in the repo.
