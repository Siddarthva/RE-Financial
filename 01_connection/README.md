# 01_connection: QuickBooks MCP connection

**Answers:** Part 1 of the brief. Connect Claude to QuickBooks through MCP and show it works, safely.
**Status key:** **Done** = built and checked; **Proposed** = design only, nothing built.

## The choice and why

Intuit's official `quickbooks-online-mcp-server`, run locally by Claude Code as a **stdio** process, **read-only**, against the Intuit **developer sandbox** only. Intuit maintains it; it is open source, so the code can be read and tested; it speaks standard MCP and handles OAuth refresh, which would otherwise be code we write and secure. Stdio means no network listener to attack. Full reasoning: [`connection_decision.md`](connection_decision.md). Setup record: [`part1-quickbooks-mcp.md`](part1-quickbooks-mcp.md).

## Rejected options

These are judgements, not benchmarks. None was built or tried.

| Option | Why not (for now) |
|---|---|
| Native Claude connector for QuickBooks | Availability for a sandbox company and its read-only controls were never established. Revisit for production. |
| Custom REST client or MCP | We would write and secure OAuth refresh, pagination, rate limits and error handling. The official server already does this and has no control we lack. |
| Third-party hosted MCP gateway | Puts client data and tokens with another party; a second vendor to vet. |
| Manual CSV or report exports | Nothing is repeatable, and it does not meet the brief to test the MCP route. |
| Enabling write tools | No requirement; a different risk class that would need its own review. |

## Architecture

```text
Claude Code  <-- stdio (JSON-RPC, MCP) -->  quickbooks-online-mcp-server (node, local)  <-- HTTPS -->  Intuit sandbox API
 tool results only                           holds .env: app keys + tokens                              Intuit sample company
```

Claude Code receives tool results only. App keys and tokens stay in the server process and its `.env`, in the server's own folder outside this project. Template config (env var names only): [`.mcp.json.example`](.mcp.json.example). The real `.mcp.json` and env files are git-ignored.

## Credential lifecycle

| Stage | What happens | Status |
|---|---|---|
| OAuth | Intuit developer app + sandbox company; redirect URI `http://localhost:8000/callback`. The server's `npm run auth` opens the browser, you approve, and the authorization code is exchanged for access and refresh tokens. | Done |
| Token storage | Tokens are saved to `.env` in the server folder (override: `QUICKBOOKS_TOKEN_STORE_PATH`). Never copied into this repo. | Done |
| Refresh | The server refreshes access tokens itself. Intuit rotates the refresh token on each refresh; the server writes the new one back, re-reading first if another process refreshed meanwhile. | Done |
| Expiry | Refresh tokens expire after a period of non-use (Intuit documents about 100 days; not re-checked). The grant must then be redone with `npm run auth`. | Done (known limit) |
| Revocation | If a secret is exposed, revoke or rotate it with the provider and re-authorize. This path is documented, **not exercised**. | Documented only |
| Guards | `CLAUDE.md` forbids reading secrets; a project hook blocks `Read`/`Grep`/`Bash` on `.env`, token and credential file names; saved evidence is redacted and checked by a test. | Done |

## Read-only enforcement and its proof

The server registers a tool only if its category is not disabled (`src/helpers/register-tool.ts` in the server clone). With `QUICKBOOKS_DISABLE_WRITE`, `_UPDATE` and `_DELETE` set to `true`, create/update/delete tools do not exist for the client. That is stronger than telling the model not to call them. It is **not** an authorization boundary: the OAuth grant itself carries accounting scope, so anyone who obtains the tokens could write to the API directly.

| Proof | Where |
|---|---|
| 71 tools registered with the three flags `true`; none is create/update/delete | [`2026-10-14/01_tools_list.response.json`](evidence/quickbooks/2026-10-14/01_tools_list.response.json), check (c) in the [dated README](evidence/quickbooks/2026-10-14/README.md) |
| Only `get_*` and `search_*` tools were called | [`connection_decision.md`](connection_decision.md) |
| The loader's write path is separate and sandbox-only; it uses a different credential file and refuses production | [`load_workbook_to_sandbox.py`](load_workbook_to_sandbox.py), [`config/qbo_write.env.example`](../config/qbo_write.env.example) |
| `CLAUDE.md` forbids flipping the flags | [`CLAUDE.md`](../CLAUDE.md) |

Not shown: a refused write attempt. No write was tried, by rule.

## Team hosting (Proposed, not built)

The server has a stdio transport only, so a shared service needs a wrapper that does not exist.

- One OAuth grant and one token store per client, in a secret manager, mounted as `QUICKBOOKS_TOKEN_STORE_PATH` for exactly one server process. Check each grant's realm ID before first use.
- One server process per client, never a shared pool: two processes refreshing one rotating token can invalidate it.
- A service identity with per-user authorization in front, so one client's books cannot be read through another's.
- TLS on any network hop, a central audit log, alerts on refresh failure and approaching expiry, a revoke-and-reauthorize runbook.
- Before production: fix the three runtime dependency findings in [`dependency_risk.md`](dependency_risk.md) and name an owner for upgrades.

## Reproduce it

Prerequisites: your own Intuit developer app and sandbox company, Node, and Intuit's server cloned and built beside this repo.

```powershell
# 1. Clone and build Intuit's server in a folder named quickbooks-online-mcp-server, then:
npm run auth                                                    # inside that folder; browser sign-in
# 2. Register it with the three disable flags set to true (see .mcp.json.example)
claude mcp list                                                 # expect: quickbooks connected
python 01_connection/qbo_test_connection.py abc --test          # expect: ok true, exit 0
python 01_connection/evidence/quickbooks/capture_dated.py       # live P&L + BS + tool list, redacted; exit 1 on any failure
python -m unittest tests.test_evidence_redaction tests.test_qbo_diagnose
```

Without the server, `--test` exits 1 and names the missing folder (`QBO_MCP_SERVER_DIR` overrides the location). No credentials are needed to read the saved evidence.

## Loading ABC totals into the sandbox (stretch, not done)

[`load_workbook_to_sandbox.py`](load_workbook_to_sandbox.py) is a separate, sandbox-only write path. `--dry-run` (default) prints 18 journal entries (one per month, `ABC-YYYY-MM`) and writes `outputs/abc/qbo_load_plan.json`; it needs no credentials. `--apply` needs a write-scoped env file outside the repo, refuses production, and is idempotent (same `DocNumber` + same lines is skipped; different lines is a `CONFLICT`). `--compare PNL.json` checks a saved P&L against the workbook. It has been tested only against an in-memory fake ([`tests/test_qbo_load.py`](../tests/test_qbo_load.py)). **No live write has been made.** The 2026-10-14 live P&L has no `Workbook Load` accounts.

## Evidence index

| Evidence | What it shows |
|---|---|
| [`evidence/quickbooks/2026-10-14/README.md`](evidence/quickbooks/2026-10-14/README.md) | Dated re-check, checks a–d, UTC times |
| [`evidence/quickbooks/2026-10-14/summary.json`](evidence/quickbooks/2026-10-14/summary.json) | Machine-readable checks and redaction counts |
| [`evidence/quickbooks/README.md`](evidence/quickbooks/README.md) | The eight pairs captured 2026-10-12 (P&L accrual and cash, GL, invoices, Balance Sheet, CompanyInfo) |
| [`evidence/quickbooks/checks.json`](evidence/quickbooks/checks.json), [`redaction_log.json`](evidence/quickbooks/redaction_log.json) | Pass/fail checks and what was redacted |
| [`evidence/quickbooks/redact_and_verify.py`](evidence/quickbooks/redact_and_verify.py) | Redaction and residual-secret check |
| [`dependency_risk.md`](dependency_risk.md) | 49 npm audit findings: 2 critical, 37 high, 10 moderate; 3 in runtime dependencies; none fixed |
| [`NETWORK_DIAGNOSTICS.md`](NETWORK_DIAGNOSTICS.md) | Connectivity checks for the Windows machine |

Limit: the sandbox holds Intuit's sample data, not ABC's. The monthly analysis reads the supplied workbook; **QuickBooks data is not an input to it.**

## Troubleshooting

`qbo_test_connection.py --test` maps server errors to these causes (first match wins) and prints the fix.

| Cause code | Typical error text | Fix |
|---|---|---|
| `server_missing` | Server folder not found | Clone, build and authorize Intuit's server, or set `QBO_MCP_SERVER_DIR` |
| `bad_client` | `invalid_client`, client ID/secret | Check the Development keys at developer.intuit.com, then `npm run auth` |
| `expired_token` | `invalid_grant`, 401, refresh failed | Refresh token expired or revoked: `npm run auth` in the server folder |
| `wrong_environment` | production, realm, 403 | Set `QUICKBOOKS_ENVIRONMENT=sandbox`, use Development keys, re-run `npm run auth` |
| `network` | `ECONNRESET`, `ETIMEDOUT`, `ENOTFOUND` | Check internet, VPN or proxy; see [`NETWORK_DIAGNOSTICS.md`](NETWORK_DIAGNOSTICS.md) |
| `not_configured` | `must be set`, `ENOENT` | Create the server's env file with the app keys, then `npm run auth` |
| `rate_or_outage` | 429, 5xx | Wait a few minutes and retest |
| `bad_request` | input validation | A bug in the test script, not in QuickBooks; report it, do not re-authorize |
| `unknown` | anything else | Run `node dist/index.js` in the server folder and read its output |
