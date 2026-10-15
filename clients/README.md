# clients: one folder per client

Each client is `clients/<id>/config.yaml` (workbook path, sheet and label names, account mapping, fiscal year) plus its workbook. `abc` uses the supplied workbook in `data/`. `xyz` and `lmn` are synthetic clients with different labels, month formats and fiscal years, proving a new client needs a config and not code. Answers the brief's multi-client requirement.

Add one in 3 steps (full recipe: [`02_skill/README.md`](../02_skill/README.md#add-a-client-in-3-steps)):

1. Copy `xyz/config.yaml` to `<id>/config.yaml`; edit it using [`02_skill/CONFIG_REFERENCE.md`](../02_skill/CONFIG_REFERENCE.md).
2. Put the workbook beside it (shape: one wide sheet, one column per month).
3. `python scripts/run_pipeline.py <id> <YYYY-MM>`; read the warnings.

Isolation test to copy: `tests/test_lmn_isolation.py`.
