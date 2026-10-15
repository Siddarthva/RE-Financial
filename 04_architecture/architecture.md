# Architecture (one page)

**Implemented** = built and tested. **Proposed** = design only. Python computes every number; Claude writes; a second agent reviews; a human signs. Detail: [`architecture_detail.md`](architecture_detail.md).

## Structure
Workbook → intake gate (stops, names the cell) → Python engine → review packet JSON → Claude drafts from the packet only → number grader + `finance-reviewer` agent → Excel pack → human approval locks the month.

## Files
`clients/<id>/` config and workbook · `src/` engine · `scripts/` pipeline, approve, `regress.py` · `.claude/` skills, hooks · `03_evals/` 33 golden cases, 19 mutants, 38 faults · `outputs/<id>/` generated files · `01_connection/` QuickBooks MCP.

## Skills
9 skills, 2 commands, 1 read-only reviewer agent. New skills follow [`authoring_kit/`](../02_skill/authoring_kit/CHECKLIST.md) and stay Draft until golden, trigger and grader cases exist.

## Memory
`CLAUDE.md` = rules; skills = procedure; `config.yaml` = client facts; `audit_log.jsonl` = what ran. **No cross-client memory**; one session per client and month.

## Hosting
**Implemented:** one laptop, MCP over stdio, no listener. **Proposed:** shared host, one MCP process and token store per client, secrets manager, central audit ([`connection_decision.md`](../01_connection/connection_decision.md) §8). QuickBooks is sandbox-only and **not** an analysis input.

## Ten clients: what changes
| | Today | At 10 | How |
|---|---|---|---|
| Credentials | 1 sandbox grant | 10 rotating tokens | One secret and process each; expiry alerts (Proposed) |
| Configs | 3, hand-built | 10 mappings to review | `CONFIG_REFERENCE.md`; human approves each |
| Runs | seconds offline | 10 in one week | Batch runner (Proposed) |
| Review capacity | 1 human per pack, unmeasured | the bottleneck | Severity ranking (Implemented) |
| Monitoring | files in `outputs/` | stale months, token age | Manifest dashboard (Proposed) |
| Cost | not measured | about 10× model calls | Measure tokens per run (Not done) |

## Data separation
| Layer | Status |
|---|---|
| Config: file per client | Implemented |
| Outputs: audit hook blocks other clients' folders (14 tests) | Implemented, this Python process only |
| Process: account or container per client | Proposed |
| Credentials: hook blocks secret files; grant per client | Hook Implemented; grants Proposed |
| Model context: one packet; skill forbids other folders | Convention, not enforced |
| Logs: audit log per client | Implemented; central log Proposed |

## What breaks first
1. **Token upkeep:** a stale token silently stops a client. *Alerts; one writer per store.*
2. **Model-layer isolation:** Claude's tools share the OS user. *Container and session per client.*
3. **Reviewer capacity:** 10 packs, one week. *Triage by severity; measure.*
4. **Account mapping:** judgement, not checkable. *Human approval; prior-month diff.*
5. **Layout:** only one wide sheet; others are refused. *Adapter per layout.*
6. **Reviewer variance and one machine:** *grader floor, human sign-off; shared host, backups.*
