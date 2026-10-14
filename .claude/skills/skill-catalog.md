# Skill Catalog

All project skills live under `.claude/skills/<skill-name>/SKILL.md`. Claude Code discovers them when it is started from the repo root. Each skill's `description` states when it should trigger. The Python analysis engine (`src/`) remains the source of truth for arithmetic.

## Skills

| Skill | Path | Use when | Primary outputs |
|---|---|---|---|
| `monthly-financial-analysis` | `.claude/skills/monthly-financial-analysis/SKILL.md` | Analyzing, auditing, or reporting on a monthly financial-statement workbook | Workbook audit, revenue/margin/OPEX trends, MoM, TTM, cash-flow availability disclosure, anomaly flags, executive commentary |
| `financial-statement-tie-out` | `.claude/skills/financial-statement-tie-out/SKILL.md` | Tying out or reconciling statements and trial balances | Check table (formula, expected, observed, difference, status) and exception list |
| `fpa-budget-variance` | `.claude/skills/fpa-budget-variance/SKILL.md` | Comparing actuals with a supplied budget, forecast, or prior period | Variance table, favourable/unfavourable conventions, top drivers |
| `fractional-cfo-insights` | `.claude/skills/fractional-cfo-insights/SKILL.md` | An owner wants a CFO-style decision brief | KPI snapshot, key movements, risks, decisions and questions |
| `month-end-close-review` | `.claude/skills/month-end-close-review/SKILL.md` | Running or reviewing a month-end close | Close checklist, reconciliation summary, exceptions, sign-off pack |
| `sec-reporting-support` | `.claude/skills/sec-reporting-support/SKILL.md` | Preparing support for SEC-related reporting | Traceability matrix, tie-outs, draft narrative marked `FOR REVIEW — NOT FILE-READY` |
| `company-context` | `.claude/skills/company-context/SKILL.md` | Scoping firm services or routing a new client task | Verified firm context and skill routing |

## Sections inside `monthly-financial-analysis`
Earlier separate analytics skills are now numbered sections of `monthly-financial-analysis`:
1. Workbook audit
2. Revenue trend
3. Profitability and margins
4. Operating expenses
5. Month-over-month rules
6. Trailing twelve months (TTM)
7. Cash flow (availability check)
8. Variance and anomaly flags
9. Executive commentary

## Selection and execution rules
- Run section 1 (workbook audit) before interpreting an unfamiliar workbook or when mapping correctness is in doubt.
- Run sections only when their required inputs exist. Do not derive cash-flow figures from income-statement data; `ABC Inc - Financial Statements.xlsx` has no cash-flow statement.
- Keep source workbooks read-only and write generated outputs to `/outputs`.
- These workflows reflect the supplied assessment brief's description of a finance-and-accounting firm serving entrepreneurs (month-end close, FP&A, fractional CFO, SEC reporting). They do not assert lending, underwriting, payment-processing, or other unverified services.
