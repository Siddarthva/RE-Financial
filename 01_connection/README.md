# 01_connection: QuickBooks MCP connection

**Answers:** Part 1 of the brief. Connect Claude to QuickBooks through MCP, show it works, and say how it is kept safe.
**Labels:** **Implemented** = built and checked; **Proposed** = design only; **Not done** = said plainly.

## Read in this order

| Question in the brief | Where |
|---|---|
| What was chosen, rejected, and why | [`connection_decision.md`](connection_decision.md) sections 1-3 (scored 3-option matrix; "what would change my mind") |
| Connect securely | sections 4-6: read-only enforcement, credential lifecycle table, 7 threats |
| Connect reliably | section 7: 12 failures, message, recovery, test |
| Where it runs for a team | section 8: diagram and 3-phase rollout (Proposed) |
| Dependency risk | [`dependency_risk.md`](dependency_risk.md): 49 npm audit findings, 2 critical, 37 high, 10 moderate; 3 in runtime dependencies; none fixed |

## Architecture today (Implemented)

```text
Claude Code <-- stdio (JSON-RPC, MCP) --> quickbooks-online-mcp-server (node, local) <-- HTTPS --> Intuit sandbox API
 sees tool results only                   holds app keys + tokens in its own folder               Intuit sample company
```

Claude Code receives tool results only. Keys and tokens stay in the server's folder, outside this repo. The real `.mcp.json` and env files are git-ignored; the template [`.mcp.json.example`](.mcp.json.example) has variable names only.

## Reproduce in 15 minutes

Prerequisites: Python 3 (tested on 3.13), Node (tested on v24), Claude Code, and **your own** Intuit developer app with a sandbox company (the server is Intuit's repo and is not in this submission). Times are estimates from the 2026-10-12 setup, not stopwatch runs.

| Min | Step | Command | Expect |
|---|---|---|---|
| 0-2 | No credentials needed: run the offline checks | `python -m unittest tests.test_qbo_diagnose tests.test_qbo_reliability tests.test_evidence_redaction` | `OK` (reliability tests need Node and use a fake server) |
| 2-4 | Failure message with no server | `QBO_MCP_SERVER_DIR=C:/nowhere python 01_connection/qbo_test_connection.py abc --test` | exit 1, `server_missing`, names the folder |
| 4-9 | Clone and build Intuit's server beside this repo | `git clone https://github.com/intuit/quickbooks-online-mcp-server` then `npm install` and `npm run build` inside it | `dist/index.js` exists |
| 9-12 | Authorize the sandbox (browser) | `npm run auth` inside the server folder; put `QUICKBOOKS_ENVIRONMENT=sandbox` and your Development keys in its env file | "tokens saved" |
| 12-13 | Register read-only | add the entry from `.mcp.json.example`, all 3 disable flags `true`; then `claude mcp list` | `quickbooks` connected |
| 13-15 | Live test | `python 01_connection/qbo_test_connection.py abc --test` | `ok: true`, exit 0 |
| optional | Dated evidence | `python 01_connection/evidence/quickbooks/capture_dated.py` | P&L, Balance Sheet, 71-tool list, redacted; exit 1 on any failure or surviving secret |

Without your own sandbox you can still read the saved evidence (no credentials needed): see the index below.

## Evidence index

| File | What it proves | Date (UTC) |
|---|---|---|
| [`evidence/quickbooks/README.md`](evidence/quickbooks/README.md) + 8 request/response pairs | Live read-only P&L (accrual, cash), GL, invoices, Balance Sheet, CompanyInfo through the MCP server | 2026-10-12 (two reports re-run 2026-10-13, same figures) |
| [`evidence/quickbooks/2026-10-14/README.md`](evidence/quickbooks/2026-10-14/README.md), `summary.json` | Checks a-d: CompanyInfo `ok`; monthly P&L Jan-Jun 2026; Balance Sheet 5,488.75 = 5,488.75; missing-server message | 2026-10-14 04:34-04:36 |
| [`evidence/quickbooks/2026-10-14/01_tools_list.response.json`](evidence/quickbooks/2026-10-14/01_tools_list.response.json) | 71 tools registered with the 3 flags `true`; none is create/update/delete | 2026-10-14 04:35 |
| `outputs/abc/qbo_status.json` | Last connection test result | latest run |
| [`evidence/quickbooks/checks.json`](evidence/quickbooks/checks.json), [`redaction_log.json`](evidence/quickbooks/redaction_log.json), [`redact_and_verify.py`](evidence/quickbooks/redact_and_verify.py) | Pass/fail checks; what was redacted; residual-secret scan | 2026-10-12 |
| [`../tests/test_qbo_reliability.py`](../tests/test_qbo_reliability.py), [`../tests/test_qbo_diagnose.py`](../tests/test_qbo_diagnose.py) | 12 failure modes behave as the reliability table says (fake server, no network) | run 2026-10-15 |
| [`../tests/test_evidence_redaction.py`](../tests/test_evidence_redaction.py) | Saved evidence holds no secret-like text | latest `regress.py` run |
| [`dependency_risk.md`](dependency_risk.md) | 49 npm findings, 3 runtime, none fixed | 2026-10-13 |
| [`part1-quickbooks-mcp.md`](part1-quickbooks-mcp.md) | Setup record (steps taken; some paragraphs predate the fix and say so) | 2026-10-12 to 14 |

**Limit:** the sandbox holds Intuit's sample data, not ABC's. The monthly analysis reads the supplied workbook; **QuickBooks data is not an input to it.**

## Loading ABC totals into the sandbox (stretch, Not done)

[`load_workbook_to_sandbox.py`](load_workbook_to_sandbox.py) is a separate, sandbox-only write path. `--dry-run` (default) prints 18 journal entries (`ABC-YYYY-MM`) and writes `outputs/abc/qbo_load_plan.json`; no credentials needed. `--apply` needs a write-scoped env file outside the repo ([`qbo_write.env.example`](qbo_write.env.example), real file in `.secrets/`), refuses production, and is idempotent. Tested only against an in-memory fake ([`tests/test_qbo_load.py`](../tests/test_qbo_load.py)). **No live write has been made.**

## Troubleshooting

`qbo_test_connection.py --test` prints a fixed, secret-free message for the first matching cause. Full message and recovery for each: `connection_decision.md` section 7.

| Symptom | Cause code | Do this |
|---|---|---|
| "server was not found" | `server_missing` | Clone Intuit's repo beside this one, or set `QBO_MCP_SERVER_DIR` |
| "not built" | `server_missing` | `npm install && npm run build` in the server folder |
| "Node.js was not found" | none | Install Node, put it on PATH |
| `invalid_client` | `bad_client` | Re-copy Development keys from developer.intuit.com, `npm run auth` |
| `invalid_grant`, 401 | `expired_token` | Token expired or revoked: `npm run auth` |
| 403, "production", realm | `wrong_environment` | `QUICKBOOKS_ENVIRONMENT=sandbox`, Development keys, `npm run auth` |
| `ECONNRESET`, `ETIMEDOUT` | `network` | Check internet, VPN, proxy; retest |
| "No response within 45 seconds" | `timeout` | Run `node dist/index.js` by hand to see why it does not start |
| 429 / 5xx | `rate_or_outage` | Wait a few minutes, retest |
| "input validation" | `bad_request` | A bug in the test script; report it, do not re-authorize |
| Anything else | `unknown` | Run `node dist/index.js` in the server folder and read its output |
| A command is "blocked by project hook" | n/a | The secrets guard matched an env/token file name in your command. Do not work around it; ask |
