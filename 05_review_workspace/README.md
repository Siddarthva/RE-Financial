# 05_review_workspace: optional review UI

**Answers:** nothing the brief requires. It is an optional extra for a reviewer.

A Streamlit app in [`app/`](app/) with seven pages: Overview, Financial Analysis, Insights & Review, Data Sources, Runs, Evaluations, and Architecture & Security. [`Home.py`](app/Home.py) is the entry point; a sidebar picks the client and period.

## The display-only rule

`app/` never calculates a financial figure. It reads JSON in `outputs/` (engine outputs, manifests, eval results, the audit log) and shows it. Every displayed number must come from one of those files ([`CLAUDE.md`](../CLAUDE.md), "UI rule"). Its buttons (run analysis, approve, reject, run golden evals, test connection) run the existing scripts as subprocesses and read the result back; they do not compute.

### How the rule is tested

[`tests/test_ui_numbers.py`](../tests/test_ui_numbers.py) has 15 tests. The ones that enforce the rule:

| Test | Guards |
|---|---|
| `test_no_page_imports_a_calculation_module` | No page imports calculation code (static check) |
| `test_clean_interpreter_loads_every_page_without_calculation_modules` | A fresh interpreter loading every page never loads `src/` calculation modules |
| `test_every_displayed_amount_and_percentage_exists_in_engine_json` | Every amount and percentage rendered exists in an engine JSON file |
| `test_overview_key_figures_equal_engine_values`, `test_revenue_by_stream_table_matches_tables_json` | Specific tiles and tables equal the engine values |
| `test_ttm_is_not_available_before_twelve_months` | The UI shows "not available", not a guessed TTM |
| `test_no_secrets_in_any_rendered_page`, `test_credentials_in_a_json_file_are_withheld` | No secret reaches a page |
| `test_empty_states_*`, `test_unreadable_json_shows_an_empty_state_not_a_traceback` | Missing or damaged files show an empty state with the path and the command that writes it |

Run it: `python -m unittest tests.test_ui_numbers` (expect 15 OK). Limits: the test checks that displayed values exist in the JSON, by value; it cannot tell whether a coincidentally equal number belongs to the right metric.

## How to run

```powershell
pip install -r requirements.txt                   # includes streamlit>=1.50,<2.0
python scripts/run_pipeline.py abc 2026-06        # generate the JSON the UI reads
streamlit run 05_review_workspace/app/Home.py
```

Without data the app shows "No clients found in outputs/" and the command to generate it. Page-by-page failure behaviour: [`workflows/f_review_workspace_ui.md`](../04_architecture/workflows/f_review_workspace_ui.md).

## Screenshots

None are committed. Run the app to see it. This README does not describe the pages' appearance, because it has not been checked in a browser for this document.
