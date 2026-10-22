# Live skill output in verification, 2026-10-22

Two live headless runs of `/monthly-analysis` with the new grade-and-retry step (`src/commentary_retry.py`), each graded again afterwards by the deterministic grader against its own review packet. Outputs went to the git-ignored `.tmp/live_2026-10-22/`; `outputs/` was not touched.

Command (abc shown; qbo_sandbox identical with `qbo_sandbox 2026-09`):

```text
claude -p "/monthly-analysis abc 2026-06 --outputs-root .tmp/live_2026-10-22" --model sonnet --output-format json \
  --allowedTools Skill "Bash(python src/monthly_review.py *)" "Bash(python src/commentary_retry.py *)" Read Write Edit Agent
```

| | abc 2026-06 (ABC workbook) | qbo_sandbox 2026-09 (live QuickBooks sandbox data, Intuit sample company) |
|---|---|---|
| First-pass grade | **PASS**, 66/66 numbers (`commentary_grade_2026-06.json`: `passed_first`) | **PASS** per the session's report (38/38 numbers); see note below |
| Retry used | **no** | **no** |
| Reviewer | `changes` (one invented cause, "because", in statement 3), then `approve` after one revision | `changes` (two Opex movements missing), then `approve` after one revision |
| Final grade (re-run here with `grade_commentary.grade` on the final text and its own packet) | **PASS**: 66/66 numbers, top-3 movements 3/3, cash and runway stated, 7 sections in order | **PASS**: 44/44 numbers, top-3 movements 3/3, cash and runway stated, 7 sections in order |
| Pack Cover | Verdict `APPROVED`; Commentary grade `passed_first (retry used: no)`; sign-off cells empty | Verdict `APPROVED`; Commentary grade `passed_first (retry used: no)`; sign-off cells empty |
| Model | `claude-sonnet-5-5` | `claude-sonnet-5-5` |
| Wall time (shell clock) | **165 s** | **175 s** |
| API time | 90.9 s | 118.3 s |
| Turns (main session) | 16 | 5 |
| Input tokens | 24 uncached + 47,152 cache writes + 505,719 cache reads | 8 uncached + 4,089 cache writes + 140,656 cache reads (main session; subagent usage is in the cost) |
| Output tokens | 6,046 | 2,222 (main session) |
| Cost (`total_cost_usd`, list price) | **$0.490** | **$0.408** |

**Not exercised live:** the retry path itself. Both first passes succeeded, so no live run sent mismatches back. The fail-then-pass and fail-twice paths are covered by `tests/test_commentary_retry.py` with fake commentary, not by a live model run. Runs were not repeated to force a failure.

**Found:** each session ran `commentary_retry.py grade` a second time after the reviewer's revision, as a check. That overwrote the first-attempt record. For abc both passes were PASS (66/66). For qbo_sandbox the saved record shows the second pass (44/44); the first pass (38/38) is known only from the session's own report. Still open: keeping a history of grade attempts in the record, instead of overwriting it.
