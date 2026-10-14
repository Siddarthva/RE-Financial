# Workflows

One page per workflow. Each covers inputs, outputs, gates, failure modes and what the user sees, idempotency, and the tests. Messages quoted in the failure tables come from runs on 2026-10-14.

| Workflow | Page | Top failure modes (all give one clear line, no traceback) | Tests |
|---|---|---|---|
| (a) Intake → calculate → flux | [a_intake_calculate_flux.md](a_intake_calculate_flux.md) | invalid client id / path traversal; unknown client or bad month; workbook refused by intake | `test_workflow_failures.Pipeline`, `test_robustness`, fault suite |
| (b) `/monthly-analysis` | [b_monthly_analysis_skill.md](b_monthly_analysis_skill.md) | intake refusal in `prepare`; missing or invalid packet, commentary or verdict in `build`; unnumbered commentary | `test_workflow_failures.SkillSteps`, `test_monthly_review` |
| (c) Approve / reject / lock | [c_approve_reject_lock.md](c_approve_reject_lock.md) | locked period; damaged decision file; verdict not approve | `test_workflow_failures.Approval`, `test_monthly_review` |
| (d) QBO test and evidence | [d_qbo_connection_and_evidence.md](d_qbo_connection_and_evidence.md) | server missing; token or keys invalid; invalid client id | `test_workflow_failures.Connection`, `test_qbo_diagnose` |
| (e) Loader dry-run / compare | [e_sandbox_loader_dry_run.md](e_sandbox_loader_dry_run.md) | bad month range; empty range; missing or invalid compare file | `test_workflow_failures.Loader`, `test_qbo_load` |
| (f) Review workspace UI | [f_review_workspace_ui.md](f_review_workspace_ui.md) | missing outputs; unreadable JSON; failed or hung script | `test_ui_numbers`, `test_workflow_failures.WorkspaceActions` |
| (g) Package submission | [g_package_submission.md](g_package_submission.md) | secret finding; output outside repo; no git | `test_workflow_failures.Packaging`, `test_scan_secrets` |

Known gap: there is no "re-run as v2" after approval. See (c) for why this was left as the owner's decision.
