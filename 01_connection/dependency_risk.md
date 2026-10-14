# Dependency risk: quickbooks-online-mcp-server

Source: `npm audit --json` run on 2026-10-13 against `package-lock.json` (nothing was fixed or changed).

Totals: 2 critical, 37 high, 10 moderate (49 in all). Of the 39 critical/high findings, **3 are in runtime dependencies**; the other 36 are dev-only (jest, ts-jest, typescript-eslint, coverage tooling).

## Runtime findings (the ones that matter)

| Package | Severity | Class | Action | Why |
|---|---|---|---|---|
| `proxy-addr` | critical | unreachable | upgrade | Pulled in by the SDK's `express`. The server runs over stdio and never starts an Express listener. Resolved by a lockfile refresh (>=2.0.8). |
| `@modelcontextprotocol/sdk` | high | unreachable | upgrade | Advisory is in the SDK's OAuth *client*; this server only uses `StdioServerTransport` (src/index.ts:438). Direct dep `^1.26.0` already allows the fix (>=1.31.0). |
| `axios` | high | runtime | upgrade | Used by `intuit-oauth` and `node-quickbooks` for outbound calls. Fix is >=1.20.0, which needs a lockfile update or an `overrides` entry. Exploit preconditions (attacker-controlled objects, URLs, redirects) were not verified. |

Classes: **runtime** = ships in production and its vulnerable code can be reached; **unreachable** = ships in production, but this server's code never calls the vulnerable path; **dev** = test/lint/build tooling only (`npm ci --omit=dev` does not install it).

Reachability for the two `unreachable` rows rests on a read of `src/` (stdio transport only), not on a runtime test.

## Dev-only critical/high findings

| Package | Severity | Class | Action |
|---|---|---|---|
| `handlebars` | critical | dev | fix |
| `@jest/console` | high | dev | fix |
| `@jest/core` | high | dev | fix |
| `@jest/environment` | high | dev | accept |
| `@jest/expect` | high | dev | accept |
| `@jest/fake-timers` | high | dev | accept |
| `@jest/globals` | high | dev | accept |
| `@jest/reporters` | high | dev | fix |
| `@jest/test-result` | high | dev | fix |
| `@jest/test-sequencer` | high | dev | fix |
| `@jest/transform` | high | dev | accept |
| `@typescript-eslint/eslint-plugin` | high | dev | fix |
| `@typescript-eslint/parser` | high | dev | fix |
| `@typescript-eslint/type-utils` | high | dev | fix |
| `@typescript-eslint/typescript-estree` | high | dev | fix |
| `@typescript-eslint/utils` | high | dev | fix |
| `babel-jest` | high | dev | fix |
| `brace-expansion` | high | dev | fix |
| `braces` | high | dev | accept |
| `expect` | high | dev | accept |
| `fast-glob` | high | dev | fix |
| `jest` | high | dev | fix |
| `jest-circus` | high | dev | fix |
| `jest-cli` | high | dev | fix |
| `jest-config` | high | dev | fix |
| `jest-environment-node` | high | dev | fix |
| `jest-haste-map` | high | dev | fix |
| `jest-message-util` | high | dev | accept |
| `jest-resolve` | high | dev | fix |
| `jest-resolve-dependencies` | high | dev | fix |
| `jest-runner` | high | dev | fix |
| `jest-runtime` | high | dev | fix |
| `jest-snapshot` | high | dev | accept |
| `jest-watcher` | high | dev | fix |
| `micromatch` | high | dev | accept |
| `typescript-eslint` | high | dev | fix |

`fix` = `npm audit` reports a non-breaking fix. `accept` = `npm audit` reports no fix (`fixAvailable: false`): `braces`/`micromatch`/`jest-*`/`expect`/`@jest/*` rest on a Jest 30 dependency chain. These run only on local developer machines and CI against files in the repo, so accept the risk until Jest ships a patched chain, then re-audit.

## Recommended order (not applied)

1. `npm update axios @modelcontextprotocol/sdk proxy-addr`, or add `axios` to `overrides` if `intuit-oauth`/`node-quickbooks` pin an old range. Then run the test suite.
2. `npm audit fix` for the dev `fix` rows, reviewing the lockfile diff first.
3. Re-run `npm audit --json`; the remaining `accept` rows should be dev-only.

## Limits

- The audit queries the live registry, so results change over time.
- The audit lists vulnerable *versions*; it does not show whether this repo's code reaches them. Only the two SDK-related rows were checked against `src/`.
