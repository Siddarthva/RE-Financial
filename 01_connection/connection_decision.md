# QuickBooks connection decision

Labels: **Implemented** = built and checked in this repo or the sandbox (file or dated result cited). **Proposed** = design only, nothing built. **Not done** = said so plainly. Brief: "connect securely and reliably... what you chose, what you rejected, and why... where this would run if a whole team needed it... how credentials are handled throughout."

## 1. Decision (Implemented)

Intuit's own `quickbooks-online-mcp-server` (clone of `github.com/intuit/quickbooks-online-mcp-server`), run locally by Claude Code over **stdio**, **read-only**, against the Intuit **developer sandbox** only. Config template: [`.mcp.json.example`](.mcp.json.example) (env var names only).

Why it wins: Intuit maintains it; the source is open, so we read and tested the read-only gate; it already does OAuth refresh and rotation (code we would otherwise write and secure); stdio means no network listener to attack; setup is the one-time `npm run auth`.

## 2. Options scored

Scores are 1 (poor) to 5 (strong). **They are my judgement, not benchmarks.** "?" means I could not establish the fact, so the score is a guess, not a finding. Only option B was built.

| Criterion | A. Native Claude connector | B. Open-source MCP (Intuit official) **chosen** | C. Custom MCP / REST client |
|---|---|---|---|
| Security | ? (3) Token held by a vendor-run service; scopes and data handling not established | 4 Local process, no listener, secrets in a file outside the repo; 49 npm audit findings on 2026-10-13, 0 critical/high after `npm audit fix` on 2026-10-22 ([`dependency_risk.md`](dependency_risk.md)) | 3 Best control in theory; every security decision becomes ours to get right |
| Read-only enforceability | ? (2) No evidence a per-category tool gate exists | 4 Write/update/delete tools are not registered when the 3 flags are `true`: 71 tools, none a writer ([`2026-10-14/01_tools_list.response.json`](evidence/quickbooks/2026-10-14/01_tools_list.response.json)). Not an authorization boundary: the OAuth grant itself can write | 5 Could register only reads. Not built |
| Maintenance | 5 Vendor-run | 3 Pull upstream, fix npm findings, track API versions | 1 OAuth refresh, pagination, throttling, API versioning all ours |
| Setup time | ? (4) Presumably click-through, if it exists for a sandbox | 3 About 15 minutes once you have a developer app (README) | 1 Days, plus tests |
| Team-hosting fit | ? (4) Vendor hosts | 2 stdio only; a shared service needs a wrapper that does not exist | 4 Designed for it from day one |
| Cost | ? (4) Unknown pricing | 5 Free open source; Intuit sandbox is free | 2 Engineer time |
| **Total (of 30)** | **? about 22** | **21** | **16** |

Evidence on A: a web search on 2026-10-15 described Intuit's official server as a local stdio preview and could not confirm an Intuit-hosted connector; the hosted offerings it found were third-party and unvetted. This session's tool list on the same date shows `mcp__quickbooks__*` tools from the local server and no first-party QuickBooks connector. So A is **not rejected as bad, only as unverified**, and its total is a guess that could beat B. I chose B because it is the only option I could verify end to end.

Dropped (judgement, none built): a third-party hosted MCP gateway (puts client tokens and data with another vendor to vet); manual CSV exports (no credentials at risk, but nothing repeatable, and the brief asks for the MCP route); enabling write tools (no requirement, different risk class).

## 3. What would change my mind

| Trigger | Switch to |
|---|---|
| Intuit or Anthropic publishes a supported hosted QuickBooks connector with sandbox support, a read-only mode and per-tenant grants | A, for team use |
| The 3 runtime npm findings prove reachable, or upstream stops maintaining the server | C (thin read-only client for the few reports we use) |
| More than about 3 clients, or non-developers must run it | Host B per client behind an authenticating wrapper (section 8) |
| A read-only guarantee stronger than tool-hiding is required | C with a read-only OAuth scope, if Intuit offers one (not checked) |

## 4. Read-only: how it is enforced

The server registers a tool only if its category is not disabled (`src/helpers/register-tool.ts` in the server clone). With `QUICKBOOKS_DISABLE_WRITE`, `_UPDATE` and `_DELETE` set to `true`, no create/update/delete tool exists for the client. That is stronger than telling the model not to call them, but it is not an authorization boundary: anyone holding the tokens can write straight to the API.

- **Implemented** — the flags are `true` in the template and are forced to `true` by `qbo_test_connection.py` on every test call. 71 tools registered, none a writer (dated check c, 2026-10-14).
- **Implemented** — `CLAUDE.md` forbids flipping them or calling write tools.
- **Not done** — a refused write attempt. None was tried, by rule.

## 5. Credential lifecycle (Implemented unless stated)

| Secret | Lives | Who can read it | Created / rotated / revoked | If leaked |
|---|---|---|---|---|
| App client ID + secret (Development keys) | Intuit developer portal; copied to the server's env file (server folder, outside this repo) | The OS user on this machine; the server process | Created in the portal; rotated by regenerating keys there and editing the env file; revoked by deleting the key. Rotation **documented, not exercised** | Attacker can start OAuth flows as our app but needs a user's consent to get tokens. Sandbox only |
| Refresh token | Server's env file / token store (`QUICKBOOKS_TOKEN_STORE_PATH`) | Same OS user; server process | Created by `npm run auth`; **rotates on every refresh** (server writes the new one back); expires after non-use (Intuit documents about 100 days, not re-checked); revoked at Intuit or by re-running auth | Full accounting access to the sandbox company until revoked, including writes via the API |
| Access token | Server memory and token store | Server process | Minted by refresh; short-lived (about 1 hour per Intuit docs, not re-checked) | Same access, for under an hour |
| OAuth authorization code | Browser redirect to `localhost:8000/callback` | The user at auth time | Single use, exchanged immediately | Useless once exchanged |
| Realm ID | Server env file, tool results | As above | Fixed per company | Identifies a company; not a credential, but redacted from evidence anyway |
| Loader write credential (stretch) | `.secrets/`, outside the read-only path ([`qbo_write.env.example`](qbo_write.env.example)) | Operator only | Separate from the read-only grant; **never used live** | Would allow writes to the sandbox |

What reaches Claude: tool results only. Tokens never enter the model context or this repo.

## 6. Threats and mitigations

| # | Threat | Mitigation | Status | Residual risk |
|---|---|---|---|---|
| T1 | Model or user reads env or token files | `CLAUDE.md` rule; `.claude/hooks/guard_secrets.py` blocks Read/Grep/Bash on secret-like names | Implemented | Hook matches names, not contents; a copy under another name evades it. (It also blocked this document's own first draft because the text said ".env": the guard works, bluntly.) |
| T2 | Secret committed to git | `.gitignore` for env/token/credential names; `scripts/scan_secrets.py` in the final check; `tests/test_scan_secrets.py` | Implemented | Scan is pattern-based |
| T3 | Secret leaks through saved evidence or error text | `redact_and_verify.py` with residual check; `tests/test_evidence_redaction.py`; `mask()` strips digit runs and long tokens from stored server messages (`tests/test_qbo_diagnose.py`, `tests/test_qbo_reliability.py`) | Implemented | A secret with an unusual shape could pass |
| T4 | Accidental or injected write to the books | 3 disable flags (71 tools, none writing); no write tool called; loader refuses production | Implemented | OAuth scope still allows writes if tokens are stolen |
| T5 | Wrong environment or company (production vs sandbox, wrong realm) | Sandbox-only rule; `wrong_environment` diagnosis; per-client realm check at connect | Rule and diagnosis Implemented; realm check **Proposed** | Nothing technical stops a human pointing the server at production today |
| T6 | Vulnerable runtime dependency | `npm audit` recorded: 49 findings, 3 runtime, judged unreachable over stdio | Assessed, **not fixed** | Becomes reachable if a network transport is added |
| T7 | Stolen laptop or shared account on the host | None beyond OS login | **Not done** | Tokens sit in plaintext on disk. Proposed: secrets manager + disk encryption |

## 7. Reliability: each failure, what the user sees, how to recover

Verified by `tests/test_qbo_diagnose.py` (message mapping) and `tests/test_qbo_reliability.py` (runs the real `test_connection()` against a fake stdio server; 9 tests, run 2026-10-15). Those tests found one bug, now fixed: a server crash used to wait the full 45 s and discard its stderr; it now fails at once with the diagnosis.

| Failure | Cause code | Message shown (abridged) | Recovery | Tested |
|---|---|---|---|---|
| Expired / revoked token | `expired_token` | "The refresh token is expired or revoked... run 'npm run auth'" | Re-authorize in browser | Yes, including a crash with `invalid_grant` on stderr |
| Wrong environment / realm | `wrong_environment` | "The token does not match the environment. Set QUICKBOOKS_ENVIRONMENT=sandbox..." | Fix env, re-auth | Yes (403 text) |
| Bad client keys | `bad_client` | "QuickBooks does not accept the app keys..." | Re-copy Development keys, re-auth | Yes |
| Server folder missing | `server_missing` | Names the folder; clone/build/auth steps | Clone Intuit's repo or set `QBO_MCP_SERVER_DIR` | Yes; live 2026-10-14 (dated check d) |
| Server not built | `server_missing` | "not built. Run 'npm install' and 'npm run build'" | Build | Yes |
| Node missing | none | "Node.js was not found..." | Install Node | Yes |
| Network down | `network` | "could not reach quickbooks.api.intuit.com. Check internet, VPN or proxy" | Fix network, retest | Yes (`ECONNRESET`) |
| No response | `timeout` | "No response within 45 seconds..." | Check network; start the server by hand | Yes (2 s timeout in test) |
| Rate limit / outage | `rate_or_outage` | "rate-limiting or having an outage. Wait a few minutes" | Wait, retest | Yes (429, 503) |
| Bad request (our bug) | `bad_request` | "a bug in this script... do not re-authorize" | Report it | Yes; this really happened 2026-10-13 |
| Server crash | from stderr, else `server_exited` | Diagnosis of stderr, else "exited unexpectedly" | Run `node dist/index.js` | Yes |
| Unknown error | `unknown` | "not recognised. Run 'node dist/index.js'..." | Read its output | Yes |

Not covered: automatic retry (the script never retries; a human reruns) and a live expired-token run (needs a deliberately revoked grant; **not done**). Exit code is 1 on any failure so callers can gate on it.

## 8. Team hosting (Proposed, nothing built)

```text
 Analyst (Claude Code) --SSO--> Gateway: authN, per-user/per-client authZ, audit log
                                  | (TLS)
             +--------------------+--------------------+
             v                    v                    v
   MCP process: client A   process: client B    process: client C     one process and
   token store A           token store B        token store C         one token store each
             |                    |                    |
             +---- secrets manager: per-client secret, readable by its process only
                                  | HTTPS
                                  v
                Intuit QuickBooks API (one OAuth grant per client company)
```

| Phase | What | Gate to move on |
|---|---|---|
| 0 Laptop (**Implemented today**) | One developer, stdio, sandbox, secrets on local disk | Done |
| 1 Shared host | One small VM or container for 2-3 trusted users; a wrapper exposes the server over authenticated HTTPS; still sandbox; disk encryption | Wrapper written and tested; tokens rotate unattended for 30 days |
| 2 Production-grade | Per-client grant, token store and process; secrets manager mounted per process; realm check at connect; central audit log of every tool call; alerts on refresh failure and token age; revoke-and-reauthorize runbook; named owner for dependency upgrades; runtime npm findings fixed | Security review; a revoke drill actually run |

Why one process per client: two processes refreshing one rotating token can invalidate it. Open questions: whether the official server's logging is enough for audit, and whether a hosted connector (option A) makes phases 1-2 unnecessary.

## 9. Limits

The sandbox holds Intuit's sample data, not ABC's. The monthly analysis reads the supplied workbook; **QuickBooks data is not an input to it.** Loading ABC into the sandbox is a stretch goal and was **not done** (see `README.md`).
