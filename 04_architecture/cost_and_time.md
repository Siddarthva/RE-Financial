# Cost and time per run: measured

**Answers:** what one live `/monthly-analysis` run costs in model tokens and wall time, and what ten clients would cost (estimate).

## Measured run

| Field | Value |
|---|---|
| Date | 2026-10-22 (UTC 2026-10-21 late evening) |
| Command | `claude -p "/monthly-analysis abc 2026-06 --outputs-root .tmp/cost_run" --model sonnet --output-format json --allowedTools Skill "Bash(python src/monthly_review.py *)" Read Write Edit Agent` |
| Model | `claude-sonnet-5-5` (all turns, including both `finance-reviewer` subagent runs) |
| Claude Code | 2.1.307 |
| Wall time | **124 s** (shell clock, start to exit) |
| API time | 108.6 s (`duration_api_ms`, includes the subagents) |
| Turns | 9 main-session turns; 2 reviewer subagents (verdict `changes`, then `approve` after one revision) |
| Input tokens | **1,059,255** in all: 46 uncached + 103,415 cache writes + 955,794 cache reads |
| Output tokens | **13,225** (of which 3,785 thinking) |
| Cost | **$0.559** (`total_cost_usd`, `costBasis: list` = API list price; on a Claude subscription this is a notional figure, not a bill) |
| Outputs | Written to a git-ignored temp folder (`.tmp/cost_run/abc/`), then deleted; `outputs/` was not touched |

**Commentary grade** (`python 03_evals/grade_commentary.py --commentary .tmp/cost_run/abc/commentary_2026-06.md`): **FAIL**, 66/67 numbers. Statement 2 says gross profit fell "(-1.62%)"; the packet has `mom_pct` −0.016149, i.e. −1.61%. Top-3 movements 3/3, cash and runway stated, all seven sections in order. The `finance-reviewer` approved the text on its second pass without catching the rounding; the deterministic grader did. The build step also reported a failed check, but its cause was not inspected before the temp outputs were deleted (the session's own summary lists it as unverified). This is the reason the grader, not the reviewer, gates the pack.

### A first attempt that did nothing

The same command without `--allowedTools` stopped after 2 turns: in `-p` mode the `Skill` call was permission-denied, and the model asked what to do instead of improvising. 12 s wall, 57,243 input (4 uncached, 14,455 cache writes, 42,784 cache reads), 620 output tokens, **$0.068**. Headless runs need the command's tools pre-approved; the measured run above is the retry with exactly the command's declared `allowed-tools` plus `Skill`.

## Ten clients: deterministic batch, measured (2026-10-22)

`python scripts/run_batch.py` runs every client in [`clients/batch.yaml`](../clients/batch.yaml) (abc, xyz, lmn, qbo_sandbox and the seven synthetic clients c04-c10: 11 clients), each in its own subprocess with its own outputs root and temp dir, no model calls. Measured on the build laptop:

| Run | Clients | Result | Wall time |
|---|---|---|---|
| `--jobs 1` (sequential) | 11 | 11/11 as declared (c07 warns about its missing month, as declared) | **75.8 s** (slowest: qbo_sandbox 22.4 s, c08 13.3 s, c09 10.9 s; wide workbooks 2.6-6.0 s) |
| `--jobs 4` | 11 | 11/11 as declared | **36.9 s** |

This is the offline engine stage only (intake, calculation, flux, packet). The model stages are the estimate below.

## Ten clients: model stages, estimate

Labelled **estimate**: one measured run, one client, one month, scaled linearly. Not measured.

| | Per client-month (measured) | 10 clients, one month each (**estimate**) |
|---|---|---|
| Cost at list price | $0.56 | about **$5.60**; about $11 if every client needed a second full run |
| Wall time, sequential | about 2 min | about **21 min**; parallel runs would be bounded by rate limits (not measured) |
| Output tokens | 13.2k | about 132k |

What would move the estimate: a reviewer loop that runs twice for every client (the run above already had one revision), larger packets for clients with more accounts, and cache hits (95% of input tokens here were cache reads; a cold cache costs more).
