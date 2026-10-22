# Changelog

## post-submission (branch `post-submission`, tag `v4.0-post-submission`, 2026-10-22)

The submitted version is unchanged: tag `v-final-submission` still points to `90259bf` on `main`. Everything below is on the `post-submission` branch only.

### Gaps closed

| Gap | Status | Where |
|---|---|---|
| 22 documentation drift items (golden table 12/12/9 = 33 and G01–G33, dates, measured runtimes, `/close-review` and owner memo exist, skill catalog 9 skills with versions and trigger files, brief_traceability counts, intake scope, SKILL.md path, workflow-failure test count, config break lab 25 entries, tag vs results) | Implemented | Phase 1 commit; item 20 (live-consistency date) needed no change, the file already discloses it |
| Count tables generated from results, not typed | Implemented | `scripts/render_counts.py` (`--check` exits 1 when stale), wired into `scripts/regress.py` as a guard |
| CI | Implemented | `.github/workflows/ci.yml`: Windows and Ubuntu, Python 3.13; unit tests, golden evals, commentary grader plus flawed control (must exit 1), doc counts, secret scan, workbook hash. No secrets in CI |
| Windows-only locked-file test passed silently on Linux | Implemented | `tests/test_robustness.py`: F31 split out, skips with a reason off Windows; Windows behaviour unchanged |
| Cost and tokens per run | Implemented | `04_architecture/cost_and_time.md`: one live Sonnet run, $0.559 list, 124 s, 1.06M input / 13.2k output tokens; ×10 clients labelled estimate |
| npm audit findings in the server clone | Implemented (local clone only) | `npm audit fix` (not `--force`): 51 → 23 findings, 0 critical, 0 high; runtime 10 → 3 moderate. Build and live read-only `--test` pass. `01_connection/dependency_risk.md` |
| Full verification | Implemented | `03_evals/FINAL_RUN.md` "post-submission run": 186 unit, 33/33 golden, 19/19 mutants, 38/38 faults, 0 silent wrong, scan 0, hash unchanged |

### Found along the way

- The measured live run's commentary **failed** the grader on one number (gross profit "−1.62%"; the packet gives −1.61%). The `finance-reviewer` subagent approved it, and the deterministic grader caught it. Recorded in `cost_and_time.md`; nothing was changed to make it pass.
- A headless `claude -p "/monthly-analysis …"` run without `--allowedTools` does nothing: the `Skill` call is permission-denied.

### Still open

| Gap | Status | Reason |
|---|---|---|
| Stretch goal: load the workbook into the sandbox and run end to end | Not done | The live write was approved at the gate on 2026-10-22, but `--apply` stopped three times before any side effect: `.secrets/qbo_write.env` was not present. Nothing was written |
| Ship the npm fix | Not done | The server clone is untracked, so a fresh clone starts from Intuit's lockfile |
| 3 runtime moderate npm findings (`intuit-oauth`, `query-string`, `decode-uri-component`) | Not done | No fix offered upstream (`fixAvailable: false`) |
| CI on Linux | Proposed until GitHub reports | It couldn't be run locally (no Linux available); the first Ubuntu result is on GitHub Actions |
| Mutation and fault injection in CI | Proposed | About 35 min; they run locally in the full `scripts/regress.py` |
| Team hosting, per-client grants and OS isolation | Proposed | Unchanged from the submission |
