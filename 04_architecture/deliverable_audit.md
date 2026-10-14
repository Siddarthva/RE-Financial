# Deliverable audit: before and after (v3.0 upgrade, 2026-10-15)

Method: for each deliverable, the brief's wording is quoted, each requirement is listed, and the files as of commit `6410527` (before) are scored **Met / Weak / Missing** with evidence. Only Weak or Missing items were changed. "After" is scored on the files in this repo at the commit that adds the row.

## D1 — `01_connection/`

Brief: "connect... securely and reliably... what you chose, what you rejected, and why... where this would run if a whole team needed it... how credentials are handled throughout".

| # | Requirement | Before | Evidence before | After | What changed |
|---|---|---|---|---|---|
| 1 | Connects to the sandbox | Met | Live `ok: true` 2026-10-14; 8 evidence pairs | Met | unchanged |
| 2 | Securely: read-only enforced, secrets kept out | Met | 71 tools, none a writer; hook; redaction test | Met | unchanged |
| 3 | Reliably: failures give a usable message | Weak | Only `diagnose()` text mapping tested (3 tests); crash, timeout, not-built, Node-missing paths untested; no table | Met | `tests/test_qbo_reliability.py` (9 tests); crash bug found and fixed (waited 45 s, dropped stderr); 12-row table |
| 4 | What you chose | Met | Decision section | Met | scored matrix added |
| 5 | What you rejected and why | Weak | 5 rejected options as unscored judgements; native connector "never established" | Met | 3-option matrix on 6 criteria, evidence for option A (search + tool list, 2026-10-15), "what would change my mind" |
| 6 | Team hosting | Weak | 5 bullets, no diagram, no phases | Met | ASCII diagram, 3 phases with gates, labelled Proposed |
| 7 | Credentials throughout | Weak | A 6-step flow; no per-secret owner/rotation/leak impact; no threat list | Met | lifecycle table (7 secrets), 7 threats with status and residual risk |
| 8 | README: reproduce, evidence, troubleshooting | Weak | Reproduce needs a pre-built server; evidence index undated | Met | 15-minute timed table (offline steps first), dated evidence index, 12-row troubleshooting |

Remaining gaps (honest): a live expired-token run and a refused-write demonstration were **not done**; option A was not tried; phases 1-2 of hosting are **Proposed**. The 15-minute figure is an estimate.
