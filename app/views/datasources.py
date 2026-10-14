import streamlit as st

import data
import ui
from views._ctx import need_client


def render():
    client = need_client()
    if not client:
        return
    ui.title("Data Sources", client)
    s = data.load_summary(client)
    st.subheader("Source workbook")
    if s.ok:
        ui.table([{"Field": k, "Value": str(s.data.get(k))} for k in
                  ("display_name", "source", "period", "months", "fiscal_year_start_month", "latest_fiscal_year")])
        ui.source_note(s.path)
    else:
        ui.empty_state("summary", s.path, s.error)

    st.subheader("QuickBooks load plan")
    lp = data.load_load_plan(client)
    if lp.ok:
        ui.table([{"Doc": e.get("doc_number"), "Date": e.get("txn_date"), "Lines": len(e.get("lines", [])),
                   "Workbook net income": e.get("net_income_workbook"), "Signature": e.get("signature")}
                  for e in lp.data])
        ui.source_note(lp.path)
    else:
        ui.empty_state("QuickBooks load plan", lp.path, lp.error)

    st.subheader("Available periods")
    periods = data.list_periods(client)
    st.write(", ".join(periods) if periods else "No review packets found.")
