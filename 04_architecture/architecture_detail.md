# Architecture detail (appendix to the one-page note)

The one-page note [`architecture.md`](architecture.md) must stay on one printed page, so the reasoning lives here. Labels: **Implemented** (built and tested), **Proposed** (design only), **Not done**.

## Structure and files

| Stage | Gate | Code | Output |
|---|---|---|---|
| 1 Intake | Sheet, header, contiguous months, totals present, amounts numeric, sections foot, gross profit and operating income tie, Balance Sheet balances and Current Year Earnings = year-to-date net income | `src/close_artifacts.py` | `intake_<m>.json` or a refusal naming the cell |
| 2 Calculate and flux | Config validated; materiality rule from config | `src/run_client.py`, `src/monthly_review.py` | `review_packet_<m>.json`, `flux_<m>.json`, `analysis.xlsx` |
| 3 Draft | Claude reads only the packet | `monthly-financial-analysis` skill | `commentary_<m>.md` |
| 4 Review | Number grader + `finance-reviewer` agent (read-only) | `03_evals/grade_commentary.py`, `.claude/agents/` | `review_<m>.json` |
| 5 Package | Sign-off pack; sign-off cells blank | `src/monthly_review.py` | `monthly_review_<m>.xlsx` |
| 6 Approve | A named human; month locked | `scripts/approve.py` | `approval_<m>.json`, manifest |

Per-stage failure messages and tests: [`workflow.md`](workflow.md), [`workflows/`](workflows/README.md).

## Skills

Nine skills (`.claude/skills/`, catalogue in `skill-catalog.md`), two commands (`/monthly-analysis`, `/close-review`), one agent (`finance-reviewer`, tools Read, Grep, Glob). Only `monthly-financial-analysis`, `flux-explanations` and `client-questions` have output graders; the others are Draft-level with trigger cases only. Trigger cases run by `03_evals/run_trigger_evals.py`.

## Memory

| Kind | Where | Scope |
|---|---|---|
| Standing rules | `CLAUDE.md` | every task: secrets, read-only workbook, evals, read-only QuickBooks, UI never calculates |
| Procedure | `.claude/skills/*/SKILL.md` (versioned, changelog) | by task |
| Client facts | `clients/<id>/config.yaml` | one client |
| History | `outputs/<id>/audit_log.jsonl`, run manifests | one client |
| Cross-client or personal memory | none, by design | a model that remembers client A while writing client B is a leak |

## Hosting

Implemented: one Windows machine, Claude Code launches the QuickBooks MCP server over stdio. No listener, no shared service, no scheduler. Proposed phases (laptop, shared host, per-client grants with secrets manager and audit logs), the diagram and the gates between phases: [`01_connection/connection_decision.md`](../01_connection/connection_decision.md) §8.

## Ten clients: what changes

| Dimension | Today (3 clients) | At 10 | How | Status |
|---|---|---|---|---|
| Credentials | One Intuit sandbox grant, read-only; the analysis reads workbooks, not QuickBooks | 10 grants; refresh tokens rotate on use and expire after non-use; one stale token silently stops one client | Per-client secret in a manager, one MCP process per client (two processes refreshing one token invalidate it), alerts on failure and token age, revoke runbook | Proposed |
| Configs | `abc`, `xyz`, `lmn`; 70, 8 and 6 account mappings | 10 configs, hundreds of mappings to judge (abc alone has 70) | Fields documented with observed failure modes (`02_skill/CONFIG_REFERENCE.md`, `config_break_lab.py`); mapping is a human judgement, shown in the pack | Implemented; mapping review is manual |
| Runs | `run_pipeline.py` about 2 s offline; a model-written commentary takes minutes (not timed) | 10 months to close in the same week | A batch runner that loops clients, one session each; the pipeline is already per-client and idempotent | Proposed |
| Review capacity | One human signs one pack; time per pack not measured | The human is the bottleneck, not compute | Flux items ranked by severity and materiality; open questions listed; capacity planning needs a measured time per pack | Ranking Implemented; measurement Not done |
| Monitoring | Files in `outputs/`; `scripts/close_review_status.py` prints a stage table per client and month | Need to see stale months, failed gates, token age at a glance | Dashboard reading the manifests (`app/` reads JSON only); alerts | Status script Implemented; dashboard and alerts Proposed |
| Cost | Python does arithmetic, so model use is wording and review only; tokens per run **not measured** | Roughly linear in clients | Log token counts per run, then set a budget | Not done |

## Data separation, layer by layer

| Layer | What separates clients | Test or evidence | Gap |
|---|---|---|---|
| Config | One `config.yaml` per client; `client` must equal the folder | `tests/test_client_isolation.py`, `config_break_lab` | none known |
| Outputs | `outputs/<id>/` only; during a run an audit hook blocks reads of other clients' folders and writes outside the client's own outputs; Windows short-name bypass closed | `tests/test_client_isolation.py` (14), `tests/test_lmn_isolation.py` (4) | Covers this Python process only; Claude's own file tools are not bound by it |
| Process | Separate invocation per client | none beyond the above | No OS account or container per client (Proposed) |
| Credentials | Secret files blocked by name by a project hook; evidence redacted; scan before release | `guard_secrets.py`, `scan_secrets.py`, `tests/test_evidence_redaction.py` | Hook matches names not contents; per-client grants Proposed |
| Model context | The model is given one packet (client, month); the skill forbids other folders | `test_client_isolation.py` proves the engine, not the model | Convention, not enforced. Two clients in one session would mix context |
| Logs | Per-client audit log and manifest | files | No central, tagged, retained log (Proposed) |

## Credential security (summary)

QuickBooks MCP runs with write, update and delete disabled (71 tools, none a writer; dated check 2026-10-14). Secrets stay outside the repo; hook and secret scan enforce it. A separate write credential exists only for the sandbox loader and was never used. Full lifecycle table, 7 threats and the reliability table: [`connection_decision.md`](../01_connection/connection_decision.md) §5-7.

## What breaks first, ranked

| # | Failure | Why it ranks here | Mitigation | Status |
|---|---|---|---|---|
| 1 | Token upkeep | Silent, per client, and expiry is calendar-driven, not load-driven | Alerts, single writer per store, revoke drill | Proposed |
| 2 | Model-layer isolation | Highest consequence: a leak across clients. The engine is separated; the model's tools are not | Container and one Claude session per client; deny rules for other clients' paths | Proposed |
| 3 | Reviewer capacity | Ten packs and one sign-off each in a few days | Severity ranking; batch triage; measure minutes per pack | Partly Implemented |
| 4 | Account mapping | Needs judgement per client; code cannot detect a wrong but valid category | Reviewer approval; diff mappings month to month | Manual |
| 5 | Layout assumption | One wide sheet with a column per month. Other shapes are refused at intake, not guessed | New adapter per layout; the intake gate and 32 faults stop silent mislabelling | Refusal Implemented; adapters Not done |
| 6 | Reviewer variance | LLM verdicts vary run to run (`03_evals/live_consistency_2026-10-15.md`: same facts, different wording, 3 of 3 runs passed) | Grader floor on numbers; human signs | Implemented |
| 7 | One machine | No backup, concurrency control or off-box audit trail | Shared host, versioned outputs | Proposed |
