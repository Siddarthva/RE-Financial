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
**Implemented:** one laptop, MCP over stdio, no listener; a launcher that starts one MCP process per client with its own credential path, working dir and token store ([`scripts/mcp_per_client.py`](../scripts/mcp_per_client.py)); QuickBooks sandbox report JSON as an analysis input (client `qbo_sandbox`; ABC still comes from the workbook). **Proposed:** shared network host with authentication and TLS, secrets manager, central audit ([`connection_decision.md`](../01_connection/connection_decision.md) §8).

## Ten clients: what changes
| | Today | At 10 | How |
|---|---|---|---|
| Credentials | 1 sandbox grant | 10 rotating tokens | One secret and process each; expiry alerts (Proposed) |
| Configs | 11 (abc, xyz, lmn, qbo_sandbox, synthetic c04-c10) | mappings to review | `CONFIG_REFERENCE.md`; human approves each |
| Runs | 11 clients in 75.8 s sequential, 36.9 s with 4 jobs (measured) | 10 in one week | [`scripts/run_batch.py`](../scripts/run_batch.py): process per client (Implemented) |
| Review capacity | 1 human per pack, unmeasured | the bottleneck | Severity ranking (Implemented) |
| Monitoring | files in `outputs/` | stale months, token age | Manifest dashboard (Proposed) |
| Cost | 124 s per run (measured) | about 10× (estimate) | [`cost_and_time.md`](cost_and_time.md) |

## Data separation
| Layer | Status |
|---|---|
| Config: file per client | Implemented |
| Outputs and source data: audit hook blocks other clients' folders, outputs and owned data (`clients/data_owners.yaml`); every ordered pair of the 11 clients (110) refused for data and outputs ([`tests/test_ten_client_isolation.py`](../tests/test_ten_client_isolation.py)) | Implemented and tested |
| Process: one subprocess, outputs root and temp dir per client in the batch; one client's failure does not stop or change others (tested) | Implemented |
| Container per client: offline engine, own client folder read-only, only own outputs writable, no network ([`deploy/compose.yaml`](../deploy/compose.yaml)) | Written and structure-tested; not built (no Docker on the build machine) |
| OS account per client; per-client OAuth grants in a secrets manager | Proposed |
| Credentials: hook blocks secret files; grant per client | Hook Implemented; grants Proposed |
| Model context: one packet; skill forbids other folders | Convention, not enforced |
| Logs: audit log per client | Implemented; central log Proposed |

## What breaks first
1. **Token upkeep:** a stale token silently stops a client. *Alerts; one writer per store.*
2. **Model-layer isolation:** Claude's tools share the OS user. *Container and session per client.*
3. **Reviewer capacity:** 10 packs, one week. *Triage by severity; measure.*
4. **Account mapping:** judgement, not checkable. *Human approval; prior-month diff.*
5. **Layout:** wide sheets, long (Account/Month/Amount) sheets and QuickBooks report JSON are supported; anything else is refused. *Adapter per layout.*
6. **Reviewer variance and one machine:** *grader floor, human sign-off; shared host, backups.*
