# 02_skill — the monthly financial analysis skill

**Answers:** the brief's "build a skill that produces a monthly financial analysis" requirement.

## What the skill does
Turns a client's monthly workbook into a reviewed analysis. Python computes every number (MoM, margins, TTM, OPEX categories, one-offs, cash runway). Claude writes numbered commentary from the computed packet only. A read-only `finance-reviewer` subagent and a deterministic grader check it. The result is an Excel sign-off pack.

## Where it lives, and why
- Skill: `.claude/skills/monthly-financial-analysis/SKILL.md` (related skills are listed in `.claude/skills/skill-catalog.md`).
- Command `/monthly-analysis`: `.claude/commands/monthly-analysis.md`. Reviewer: `.claude/agents/finance-reviewer.md`.
- It stays under `.claude/` at the repo root because that is where Claude Code discovers project skills, commands, agents and hooks. The engine it drives is in `src/`.

## How to run it
- In Claude Code, from the repo root: `/monthly-analysis abc 2026-06` (analyse, draft, review, build the pack). There is no `/close-review` slash command in this repo; the month-end close review is the `month-end-close-review` skill, which Claude loads when asked for a close review.
- Without Claude: `python src/run_client.py abc` (engine only) or `python scripts/run_pipeline.py abc 2026-06` (engine, packet, manifest). Outputs go to `outputs/<client>/`.

## Add a client in 3 steps
1. Copy `clients/xyz/config.yaml` to `clients/<id>/config.yaml`. Set the workbook path, sheet names, row labels, month format, account-to-category map and fiscal-year start.
2. Put the client's workbook where the config says. Never edit a source workbook.
3. Run `python src/run_client.py <id>`, then `/monthly-analysis <id> <YYYY-MM>`. No code changes; `xyz` is the proof.

## `sample_outputs/` — abc, 2026-06
| File | What it is |
|---|---|
| `monthly_review_2026-06.xlsx` | Excel sign-off pack (summary, commentary sign-off, numbers check) |
| `commentary_2026-06.md` | Reviewed numbered commentary |
| `flux_2026-06.json` | Month-over-month flux (largest movements) |

These are copies of files in `outputs/abc/`. **No separate owner memo exists in the repo**, so none is included here.
