# Connection Architecture

How Claude Code reaches QuickBooks, how credentials are kept out of reach, and how read-only is enforced. Status key: **Implemented** is built and checked in this repo; **Proposed** is a design only.

## Component diagram (Implemented)

```mermaid
flowchart TB
    U["Reviewer"] --> CC["Claude Code<br/>(one Windows machine)"]
    CC -->|"stdio, MCP tool calls"| MCP["quickbooks-online-mcp-server<br/>Intuit, local process"]
    MCP -->|"HTTPS, OAuth 2.0"| QBO["QuickBooks Online<br/>developer sandbox"]
    MCP --- TS[("Token store file<br/>outside this repo")]
    CC -. "hook blocks reads of<br/>secret and token file names" .-> TS
    CC --> OUT["outputs/ evidence<br/>redacted, tested"]
    WB[("Supplied ABC workbook<br/>read-only")] --> ENG["Python engine"]
    ENG --> OUT
```

Claude Code only ever receives tool results. The tokens stay inside the server process and its token store. No network listener exists, so nothing is exposed to attack. The workbook feeds the analysis; QuickBooks does not.

## Credential lifecycle (Implemented)

```mermaid
sequenceDiagram
    participant D as Developer
    participant S as MCP server
    participant B as Browser
    participant I as Intuit OAuth
    D->>S: run auth command
    S->>B: open consent page
    B->>I: approve the sandbox company
    I-->>S: authorization code (localhost:8000/callback)
    S->>I: exchange code
    I-->>S: access token + refresh token
    S->>S: save to token store (server folder, not this repo)
    loop every API call
        S->>I: refresh access token when expired
        I-->>S: new access token + rotated refresh token
        S->>S: write the new refresh token back to the store
    end
    Note over S,I: Refresh tokens expire after a period of non-use. The grant must then be redone in a browser.
```

Guards around the lifecycle: `CLAUDE.md` forbids reading secrets; a project hook blocks `Read`, `Grep` and `Bash` on secret, token and credential file names; saved evidence is redacted and a test checks it; the tracked-file secret scan found 0 findings in {{scan_files}} files.

## Read-only enforcement

The server registers a tool only if its category is not disabled. With `QUICKBOOKS_DISABLE_WRITE`, `QUICKBOOKS_DISABLE_UPDATE` and `QUICKBOOKS_DISABLE_DELETE` all set to `true`, create, update and delete tools **do not exist** for the client. That is stronger than telling the model not to call them.

| Layer | Control | Status |
|---|---|---|
| Server | Three disable flags set to `true`; write tools never registered | Implemented |
| Project rule | `CLAUDE.md` forbids flipping the flags or calling write tools | Implemented |
| Live check | 71 tools listed, none create, update or delete (2026-10-14) | Implemented |
| Credential | A separate write credential kept apart from the read-only one | **Not applied** |

Limit: this is not an authorization boundary. The OAuth grant itself carries accounting scope, so anyone who obtains the tokens could write directly to the API.

## Team hosting (Proposed)

Nothing here is built. The server speaks stdio only, so a shared service needs a wrapper that does not exist yet.

```mermaid
flowchart TB
    SM[("Secret manager<br/>one grant per client")]
    subgraph SVC["Service identity (not a developer session)"]
        direction LR
        A1["Server process A<br/>token store A"]
        A2["Server process B<br/>token store B"]
        A3["Server process N<br/>token store N"]
    end
    SM --> SVC
    A1 --> QA["Client A company"]
    A2 --> QB["Client B company"]
    A3 --> QN["Client N company"]
    AUTHZ["Per-user authorization"] --> SVC
    SVC --> LOG[("Central audit log<br/>alerts on refresh failure")]
```

- One OAuth grant and one token store per client, mounted for exactly one server process, because two processes refreshing one rotating token can invalidate it.
- Verify each grant's realm ID against the expected company before first use.
- TLS on any network hop, a central audit log, alerts on refresh failures and approaching expiry, and a documented revoke-and-reauthorize runbook.
- Before production: fix the three runtime dependency findings in the dependency-risk note and decide who owns upgrades.

## Evidence summary (2026-10-14, read-only)

| Check | Result |
|---|---|
| (a) CompanyInfo read | PASS |
| (b) Monthly P&L Jan–Jun 2026 and Balance Sheet at 30 Jun 2026 | PASS; the balance sheet balances at 5,488.75 |
| (c) Tools registered | PASS; 71 tools, none create, update or delete |
| (d) Missing server folder | PASS; an actionable message and exit code 1 |
| Earlier failure (2026-10-13) | A script bug, not an expired token: the server's tools take `{"params": {...}}` and the script sent `{}`. Fixed; failures are now classified with a next step |

## Rejected options

| Option | Why not (for now) |
|---|---|
| Native Claude connector for QuickBooks | Availability for a sandbox company and its read-only controls were never established |
| Custom QuickBooks REST client or MCP | We would own OAuth refresh, pagination and rate limits; the official server already does this |
| Third-party hosted MCP gateway | Puts client data and tokens with another party and adds a vendor to vet |
| Manual CSV or report exports | Not repeatable, and does not meet the brief to test the MCP route |
| Enabling write tools | No requirement; posting entries is a different risk class |

These are judgements, not benchmarks; none was built or tried.
