# AI Solutions Builder — reviewer guide

This repo is a submission for RE Financial Services' "Build Exercise — AI Solutions Builder". It does three things. It connects Claude to a QuickBooks sandbox over a read-only MCP server. It turns a monthly financial workbook into a reviewed trend analysis (revenue, margins, operating expenses, MoM, TTM, commentary) through a Claude skill, where Python computes every number and the model only writes and reviews text. It proves the analysis with golden cases, a commentary grader and a mutation test. The source workbook is never modified. Everything runs offline on the supplied workbook; you need no QuickBooks account or API key to check it.

## Deliverables

| Brief part | Folder | Key file |
|---|---|---|
| 1. QuickBooks ↔ Claude connection | [`01_connection/`](01_connection/) | [`connection_decision.md`](01_connection/connection_decision.md) |
| 2. Monthly trend-analysis skill | [`02_skill/`](02_skill/) | [`.claude/skills/monthly-financial-analysis/SKILL.md`](.claude/skills/monthly-financial-analysis/SKILL.md), [`02_skill/README.md`](02_skill/README.md) |
| 3. Evals (≥5 golden cases + grading) | [`03_evals/`](03_evals/) | [`golden_cases.json`](03_evals/golden_cases.json), [`GRADING.md`](03_evals/GRADING.md) |
| 4. One-page architecture | [`04_architecture/`](04_architecture/) | [`architecture.md`](04_architecture/architecture.md) |
| Requirement-by-requirement status | [`04_architecture/`](04_architecture/) | [`brief_traceability.md`](04_architecture/brief_traceability.md) |
| Close workflow (6 stages) | [`04_architecture/`](04_architecture/) | [`workflow.md`](04_architecture/workflow.md) |
| Optional review UI | [`05_review_workspace/`](05_review_workspace/) | [`app/Home.py`](05_review_workspace/app/Home.py) |

## Latest results (2026-10-14, from [`FINAL_RUN.md`](03_evals/FINAL_RUN.md))

| Check | Result |
|---|---|
| Unit tests (includes 15 UI tests) | 102 run, 102 OK |
| Golden cases | 18 / 18 (`workbook` 4: G01, G02, G03, G06; `workbook+perturbation` 5: G04, G05, G07, G08, G14; ABC cell-sourced 9: G09–G13, G15–G18) |
| Mutation test | 13 / 13 mutants caught, 0 survived |
| Commentary grader (engine text, reviewed text, saved skill output) | all three PASS |
| Source workbook SHA-256 | unchanged (`75da8d679a89551f…`) |
| Secret scan (156 tracked files) | 0 findings |
| Live QuickBooks read-only test (`qbo_test_connection.py --test`) | passed 2026-10-14 03:49 UTC (`ok: true`, CompanyInfo, 'Sandbox Company US a3a1'); 8 evidence pairs saved |

These results prove the checks pass on the supplied workbook and that the read-only QuickBooks test passed on the date shown. They do not prove that commentary is insightful.

## 5-minute quickstart (no QuickBooks credentials)

Python 3.11+; built on 3.13 and Windows 11. From the repo root:

```powershell
pip install -r requirements.txt
python -m unittest discover -s tests          # ~1 min, expect: OK (102 tests)
python 03_evals/run_golden_evals.py            # expect: Score: 18/18
python scripts/run_pipeline.py abc 2026-06     # intake gate + calculate + flux -> outputs/abc/
python 03_evals/grade_commentary.py            # grades the engine's own commentary: PASS
streamlit run 05_review_workspace/app/Home.py  # optional UI, reads outputs/ only
python 03_evals/mutation_test.py               # optional, ~6 min: expect 13/13 mutants caught
```

Then open [`02_skill/sample_outputs/`](02_skill/sample_outputs/) (Excel sign-off pack, commentary, flux) to see what a reviewer receives. In Claude Code, `/monthly-analysis abc 2026-06` runs the full draft-and-review flow.

## What's not done

- **Stretch goal not done.** The workbook was never loaded into the sandbox and the skill was never run through the live connection. The loader and an 18-entry dry-run plan exist and are tested against a fake; no live write has been made.
- **Live connection needs your own setup.** Eight live read-only calls are saved (2026-10-12, secrets redacted) and `--test` passed again on 2026-10-14 (03:49 UTC). A reviewer cannot repeat it without their own Intuit sandbox, the MCP server (below) and `npm run auth`. Without them, `--test` says what is missing.
- **Team hosting and ten-client isolation are designs, not builds.** Two clients exist. Isolation is an in-process audit hook plus per-client folders, not an OS or credential boundary.
- **The MCP server is not in this repo.** It is Intuit's repository, cloned beside it and untracked. Clone, build and authorize it to reproduce the connection. `01_connection/dependency_risk.md` covers its 49 npm audit findings (none fixed).
- **Different layouts need code.** `clients/xyz` shows a new client needs only a config, but the parser expects a wide sheet with one column per month.
- **Commentary quality is only partly graded.** Numbers and coverage are checked by code; usefulness and causes rest on an LLM reviewer and a human.

Full detail, with a reason for every item: [`04_architecture/brief_traceability.md`](04_architecture/brief_traceability.md).

## Repo map

| Path | Contents |
|---|---|
| [`01_connection/`](01_connection/) | MCP decision, redacted evidence, connection test, sandbox loader |
| [`02_skill/`](02_skill/) | How the skill runs and scales; sample outputs |
| [`03_evals/`](03_evals/) | Golden cases, graders, mutation test, run records |
| [`04_architecture/`](04_architecture/) | Architecture, workflow, traceability |
| [`05_review_workspace/`](05_review_workspace/) | Optional Streamlit UI (display only) |
| [`data/`](data/) | Source workbook (read-only) |
| [`src/`](src/) | Deterministic analysis engine |
| [`tests/`](tests/) | Unit tests |
| [`clients/`](clients/) | One config per client (`abc`, synthetic `xyz`) |
| [`scripts/`](scripts/) | Pipeline, approval, eval export, secret scan, `package_submission.py` |
| [`config/`](config/) | Template for the sandbox write credential |
| [`outputs/`](outputs/) | Generated files, one folder per client |
| [`.claude/`](.claude/) | Skills, `/monthly-analysis`, reviewer agent, safety hooks |
| [`CLAUDE.md`](CLAUDE.md) | Standing rules: secrets, read-only workbook, read-only QuickBooks |

`python scripts/package_submission.py` builds `dist/submission.zip` from git-tracked files after a clean secret scan.
