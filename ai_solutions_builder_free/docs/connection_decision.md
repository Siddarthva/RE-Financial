# QuickBooks connection decision

Status key: **[Done]** built and checked in this repo or sandbox; **[Proposed]** a design, nothing built.

## Decision

Use Intuit's own `quickbooks-online-mcp-server` (clone origin `github.com/intuit/quickbooks-online-mcp-server`), run locally by Claude Code as a **stdio** MCP process (config template: `.mcp.json.example`, env var names only), **read-only**, against the Intuit **developer sandbox** only.

Why: Intuit maintains it, and it is open source, so the code can be read and tested. It speaks standard MCP and handles OAuth refresh, which would otherwise be our code to write and secure. Stdio means no network listener, so nothing is exposed to be attacked.

## Read-only: how it is enforced

The server registers a tool only if its category is not disabled. With `QUICKBOOKS_DISABLE_WRITE`, `_UPDATE` and `_DELETE` set to `true`, create/update/delete tools do not exist for the client. That is stronger than telling the model not to call them. It is still not an authorization boundary: the OAuth grant itself carries accounting scope, so anyone who obtains the tokens could write directly to the API.

- **[Done]** The three flags are recorded as `true` in `docs/part1-quickbooks-mcp.md` and `CLAUDE.md` forbids changing them. I did not re-read the live registration today, to avoid printing its environment.
- **[Done]** Only `get_*`/`search_*` tools were called.

## Rejected options

These are judgements, not benchmarks; none was built or tried.

| Option | Why not (for now) |
|---|---|
| Native Claude connector for QuickBooks | Availability for a sandbox company and its read-only controls were never established. Revisit for production if it proves supported. |
| Custom QuickBooks REST client or MCP | We would write and secure OAuth refresh, pagination, rate-limit and error handling. The official server already does this and has no control we lack. |
| Third-party hosted MCP gateway | Puts client financial data and tokens with another party and makes it a second vendor to vet. |
| Manual CSV or report exports | No credentials to protect, but nothing is repeatable, and it does not meet the brief to test the MCP route. |
| Enabling write tools | No requirement. Posting entries is a different risk class and would need its own review. |

## Credential flow

1. **[Done]** An Intuit developer app (client ID and secret) and a sandbox company. Redirect URI `http://localhost:8000/callback`.
2. **[Done]** The server's auth command opens the browser; you approve; the authorization code is exchanged for an access token and a refresh token, which are saved to `.env` in the server's folder (it has its own folder, outside this project).
3. **[Done]** At run time the server refreshes access tokens itself. Intuit rotates the refresh token on each refresh; the server writes the new one back to its token store and re-reads it first if another process refreshed meanwhile. The store location can be overridden with `QUICKBOOKS_TOKEN_STORE_PATH`.
4. **[Done]** Claude Code only receives tool results. Tokens stay in the server process and the `.env`.
5. **[Done]** Guards: `CLAUDE.md` forbids reading secrets, and a project hook blocks `Read`/`Grep`/`Bash` on `.env`, token and credential file names. Saved evidence in `evidence/quickbooks/` is redacted and checked by a test.
6. **Evidence:** a monthly P&L (Jan–Jun 2026) and a Balance Sheet (30 Jun 2026) were read live through Claude Code on 2026-10-12 and re-run on 2026-10-13. This replaces the earlier "not verified" status.

Limits: the sandbox company holds Intuit's sample data, not ABC's. The monthly analysis reads the supplied workbook; **QuickBooks data is not yet an input to the analysis.** Refresh tokens expire after a period of non-use (the code reads `x_refresh_token_expires_in`; Intuit documents about 100 days, not re-checked), after which the grant must be redone in a browser.

## Team hosting [Proposed]

Nothing below is built. The server has a stdio transport only, so a shared service needs a wrapper that does not exist yet.

- **Per-client isolation of credentials:** one grant and one token store per client company, kept in a secret manager and mounted as `QUICKBOOKS_TOKEN_STORE_PATH` for exactly one server process. Verify each grant's realm ID against the expected company before first use.
- **Single writer per token store:** two processes refreshing one rotating token can invalidate it. Run one server process per client, not one shared pool.
- **Identity:** run under a service identity, not a developer's session, with per-user authorization in front so the service cannot be used to read another client's books.
- **Operations:** TLS on any network hop, central audit log of tool calls, alerting on refresh failures and approaching expiry, a documented revoke-and-reauthorize runbook.
- **Before production:** fix the three runtime dependency findings in `quickbooks-online-mcp-server/docs/dependency_risk.md` and decide who owns upgrades.
- **Open questions:** whether the official server's logging is enough for audit, and whether a supported hosted connector makes all of this unnecessary.
