# 00_START_HERE

Submission for the RE Financial Services build exercise. Seven PDFs, generated from the repo's Markdown by one command.

## Read in this order

| # | PDF | Pages | What it is |
|---|---|---|---|
| 1 | `00_Submission_Overview.pdf` | 2 | What was built, the deliverables map, the results, what is not done |
| 2 | `04_Architecture_OnePage.pdf` | 1 | The official Part 4 note, rendered from `04_architecture/architecture.md` |
| 3 | `01_Connection_Architecture.pdf` | 4 | Component and credential diagrams, read-only enforcement, team hosting (proposed), evidence |
| 4 | `02_Skill_and_Analysis_Workflow.pdf` | 4 | End-to-end flow, skill anatomy, client-config model, sample output |
| 5 | `03_Evals_and_Regression.pdf` | 4 | Eval layers, golden cases, mutation and robustness results, regression procedure |
| 6 | `06_Verification_and_Robustness_Report.pdf` | 8 | Brief-to-proof matrix and the 32-fault robustness report, with dates |
| 7 | `05_Workflows_Appendix.pdf` | 20 | Seven workflow pages with diagrams (supplementary to the one-page note) |

## Rebuild

```
pip install -r scripts/requirements-pdf.txt
npm install --prefix scripts/.pdf_cache mermaid@10.9.3
python scripts/build_pdfs.py
```

Needs Edge or Chrome. The script builds all seven, then checks page counts (the one-pager must be one page), looks for raw Markdown or Mermaid syntax, counts diagrams, and rasterises page 1 of each PDF into `scripts/.pdf_cache/png/`. Authored pages live in `src/`; the other PDFs come straight from the repo's existing docs. Run counts in `00`–`03` are read from `03_evals/FINAL_RUN.md`, so they cannot drift from it.

The PDF footer shows the commit SHA, with `+uncommitted` when the working tree has changes, and the commit date.
