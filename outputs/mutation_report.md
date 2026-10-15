# Mutation test report

| Mutation | Module | Caught? | By which test |
|---|---|---|---|
| Reverse month order | `financial_analysis.py` | ✅ yes | G01, G03, G07, G14, test_mom_revenue_change |
| Reverse month order | `abc_workbook_adapter.py` | ✅ yes | G09, G10, G11, G12, G13, G15, G16, G17, G18, G21, G23, G24, G26, G27, G28, G31, G32, test_bug5_category_mom_pct_sign_uses_absolute_prior |
| Flip revenue sign | `financial_analysis.py` | ✅ yes | G01, G02, G03, G07, G14, test_margin_calculation |
| Flip revenue sign | `abc_workbook_adapter.py` | ✅ yes | G11, G13, G18, G31, test_ttm_available_for_twelve_consecutive_months |
| Sum subtotals twice | `abc_workbook_adapter.py` | ✅ yes | test_opex_categories_sum_to_total_operating_expenses_every_month |
| Shift months by one | `financial_analysis.py` | ✅ yes | G14 |
| Shift months by one | `abc_workbook_adapter.py` | ✅ yes | G09, G10, G11, G12, G13, G15, G16, G17, G18, G21, G23, G24, G26, G27, G28, G31, G32, test_bug3_rows_after_total_operating_expenses_are_not_opex |
| Drop one opex category | `financial_analysis.py` | ✅ yes | G06, test_category_mom |
| Drop one opex category | `abc_workbook_adapter.py` | ✅ yes | test_bug2_expense_trends_do_not_depend_on_module_global |
| TTM over 11 months | `financial_analysis.py` | ✅ yes | G03, test_ttm_only_after_12_months |
| TTM over 11 months | `abc_workbook_adapter.py` | ✅ yes | G11, G13, test_ttm_available_for_twelve_consecutive_months |
| Wrong margin denominator (gross profit / COGS) | `financial_analysis.py` | ✅ yes | G02, test_margin_calculation |
| Wrong margin denominator (gross profit / COGS) | `abc_workbook_adapter.py` | ✅ yes | G13, G18, G31, test_approved_pack_has_blank_signoff_and_open_questions |
| Flux ignores the percentage threshold | `close_artifacts.py` | ✅ yes | test_flux_needs_both_the_dollar_and_the_percent_threshold |
| Year-over-year compares with last month | `monthly_review.py` | ✅ yes | G31, test_approved_pack_has_blank_signoff_and_open_questions |
| Adjusted net income sign reversed | `monthly_review.py` | ✅ yes | G32, test_adjusted_net_income_removes_one_offs |
| Balance Sheet tie-out tolerance made huge | `close_artifacts.py` | ✅ yes | G23, G24, test_current_year_earnings_mismatch_fails |
| Section footing check made blind | `close_artifacts.py` | ✅ yes | G21, test_line_that_does_not_foot_stops |
| Prior-month column no longer required | `close_artifacts.py` | ✅ yes | G19, test_missing_prior_month_stops |

19/19 mutants caught; 0 survived.
