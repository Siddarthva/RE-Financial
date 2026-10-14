---
name: <kebab-case-skill-name>
description: Use when <the situations, in the user's words, that should trigger this skill>. Do not use when <the closest look-alike that should NOT trigger it>.
---

# <Skill title>

## When to trigger
- Positive: <3+ example requests that must trigger this skill>
- Negative: <1+ example request that must NOT trigger it, and which skill handles it instead>

## Inputs
- <Required file / JSON packet / client + month>, and where it lives (path under `outputs/<client>/`)
- If an input is missing: <stop and say what is missing; never guess>

## Procedure
1. <Run the Python engine / read the packet. Python computes every number.>
2. <Step that turns packet values into the deliverable>
3. <Step that checks the result against the packet>

## Never do
- Invent a cause, a number, or a source cell. Write only about numbers in the packet.
- Modify the source workbook or any expected eval value.
- Read or print secrets (environment files, tokens, auth codes).
- <Skill-specific prohibition>

## Output format
<Exact sections / columns / file name and location under `outputs/`.>

## Evals
- Golden cases: <IDs in 03_evals/golden_cases.json (3+ on real ABC data)>
- Trigger cases: <file in 03_evals/skill_triggers/ (3+ positive, 1+ negative)>
- Grader: <script that checks this skill's output>

## Version
<major.minor> — <date>

## Changelog
- <major.minor> (<date>): <what changed and why>
