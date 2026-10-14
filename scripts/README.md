# scripts — command-line entry points

- `run_pipeline.py` — engine, then review packet and run manifest.
- `approve.py` — approve or reject a period; writes the audit log.
- `export_eval_results.py` — eval summary JSON for the review workspace.
- `scan_secrets.py` — secret scan; never prints values.
- `package_submission.py` — zip of git-tracked files, built only after a clean secret scan.

Connection scripts live in `01_connection/`.
