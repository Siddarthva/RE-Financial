# Part 1 — QuickBooks MCP Integration Record

## Implemented locally
- Created the Intuit developer app and QuickBooks Online sandbox company.
- Registered Development redirect URI `http://localhost:8000/callback`.
- Cloned Intuit's official `quickbooks-online-mcp-server` repository, installed dependencies, and completed the TypeScript build.
- Completed the repository's OAuth flow; its auth command reported that tokens were saved to `.env`.
- Checked required environment-variable presence without displaying values.
- Confirmed `QUICKBOOKS_DISABLE_WRITE=true`, `QUICKBOOKS_DISABLE_UPDATE=true`, and `QUICKBOOKS_DISABLE_DELETE=true`.
- Registered a user-scoped stdio MCP server named `quickbooks`; `claude mcp list` reported it as connected.

## Current status
- **Live test passes.** `python 01_connection/qbo_test_connection.py abc --test` returned `ok: true` on 2026-10-14 (03:49 UTC): "Connected. Read-only CompanyInfo query succeeded." (sandbox company "Sandbox Company US a3a1").
- **Evidence:** 8 redacted request/response pairs in `01_connection/evidence/quickbooks/` (captured 2026-10-12; two reports re-run 2026-10-13 with identical figures).
- **Not shown:** a write path (disabled by design) and the cause of the earlier `ECONNRESET`.

## Decision and alternatives
**Selected:** official open-source Intuit MCP server, run locally over stdio.

**Why:** less custom code to maintain, standard MCP interface, inspectable implementation, direct fit for the assessment, and works with a sandbox OAuth grant.

**Considered:**
- **Native connector:** potentially lower operational overhead if the target Claude environment offers a supported QuickBooks connector with the required sandbox access. Availability and sandbox suitability were not established in this setup.
- **Custom API/MCP:** offers more control over tool schemas and authorization, but adds OAuth refresh, pagination, error handling, API-versioning, testing, and security burden. Not justified for this prototype unless the official server lacks a required control.

## Safe verification sequence
1. Diagnose local DNS/TCP reachability to `api.anthropic.com:443` without changing credentials.
2. Confirm Claude Code account/auth status using `claude` and `/status`; do not set `ANTHROPIC_API_KEY` unless intentionally choosing API billing.
3. Run `claude mcp list` and confirm `quickbooks` remains connected.
4. Inside Claude Code, inspect available QuickBooks MCP tools and choose a read-only company/query/list operation.
5. Execute one read-only request and record the tool name, non-sensitive result summary, and timestamp. Never capture tokens or authorization codes.
6. If the call fails, record the sanitized error and do not claim end-to-end success.

## Credential controls
- `.env` remains inside the separate MCP repository and must not be copied into this project or committed.
- Never paste `.env` values, OAuth authorization codes, access tokens, or refresh tokens into chat, issues, screenshots, or logs.
- If a secret is exposed, revoke/rotate it in the relevant provider and reauthorize.
- Keep all three write/update/delete disable flags set to `true`. Do not use create/update/delete tools for the assessment.
- Use only the developer sandbox; do not connect a real QuickBooks company or real client data.

## Team hosting answer
For a team, deploy the MCP/API integration as an authenticated service in a managed runtime, with TLS, managed secrets, per-user/tenant authorization, audit logs, monitoring, and controlled token refresh. Do not share a developer's local `.env`. Verify each OAuth grant's realm/company and enforce tenant checks server-side.
