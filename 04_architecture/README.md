# 04_architecture: design, workflow and traceability

**Answers:** the brief's architecture questions (hosting, ten-client isolation, credential security, what breaks first) and the proof that the design matches the code.

## Index

| Document | Read it for | Evidence it rests on |
|---|---|---|
| [`architecture.md`](architecture.md) | The one-page note: structure, what the model sees, hosting, ten-client isolation, credential security, memory, what breaks first. Each point is marked **Implemented** or **Proposed**. | `src/`, `tests/test_client_isolation.py`, [`01_connection/`](../01_connection/README.md) |
| [`workflow.md`](workflow.md) | The six-stage monthly close (intake gate → calculate and flux → skill draft → reviewer → package → human approval and lock), with the gate at each stage and who acts | `scripts/run_pipeline.py`, `src/monthly_review.py`, `scripts/approve.py` |
| [`workflows/`](workflows/README.md) | One page per workflow (a–g): inputs, outputs, gates, failure messages, idempotency, tests | [`tests/test_workflow_failures.py`](../tests/test_workflow_failures.py) (12 tests) |
| [`verification_matrix.md`](verification_matrix.md) | Every line of the brief mapped to a command or file and its result from a clean-state run on 2026-10-14 | Commands listed in the matrix |
| [`brief_traceability.md`](brief_traceability.md) | Each requirement, where it is answered, Done / Partial / Not done, and why | The files it names |

### Workflow pages

| Workflow | Page |
|---|---|
| (a) Intake → calculate → flux | [`a_intake_calculate_flux.md`](workflows/a_intake_calculate_flux.md) |
| (b) `/monthly-analysis` | [`b_monthly_analysis_skill.md`](workflows/b_monthly_analysis_skill.md) |
| (c) Approve / reject / lock | [`c_approve_reject_lock.md`](workflows/c_approve_reject_lock.md) |
| (d) QuickBooks test and evidence | [`d_qbo_connection_and_evidence.md`](workflows/d_qbo_connection_and_evidence.md) |
| (e) Sandbox loader dry-run / compare | [`e_sandbox_loader_dry_run.md`](workflows/e_sandbox_loader_dry_run.md) |
| (f) Review workspace UI | [`f_review_workspace_ui.md`](workflows/f_review_workspace_ui.md) |
| (g) Package submission | [`g_package_submission.md`](workflows/g_package_submission.md) |

## PDFs

The one-page note is rendered to a PDF at [`00_START_HERE/04_Architecture_OnePage.pdf`](../00_START_HERE/04_Architecture_OnePage.pdf) by `scripts/build_pdfs.py`, which checks that it is exactly one page.

## What this folder proves, and what it doesn't

- **Proves:** the design matches what the code does. Items marked **Proposed** (team hosting, per-client credentials, OS-level isolation, ten clients) are designs, not builds.
- **"Doc review only"** in the verification matrix means a document's content meets the line; no command can prove it.
- **Known gap:** there is no "re-run as v2" after approval. See [workflow (c)](workflows/c_approve_reject_lock.md).
- **Not checked by anyone:** G10–G18 cell by cell against the workbook.

- [`final_review.md`](final_review.md) — independent cold review of the submission and what was fixed after it.
