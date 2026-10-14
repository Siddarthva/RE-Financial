import streamlit as st

import ui


def render():
    ui.title("Architecture & Security")
    st.subheader("Data flow")
    st.markdown(
        "1. **Engine** reads the source workbook and writes JSON under `outputs/<client>/`.\n"
        "2. **Reviewer** produces a structured review of the engine review packet.\n"
        "3. **Evals** check commentary figures against engine output.\n"
        "4. **This workspace** reads those JSON files and displays them. It performs no calculations."
    )
    st.subheader("Controls")
    st.markdown(
        "- **Display only:** `app/data.py` is the sole loader; pages never compute financial figures.\n"
        "- **Source workbook is read-only:** generated files go to `outputs/` only.\n"
        "- **QuickBooks access is read-only:** write, update and delete are disabled by configuration.\n"
        "- **Secrets:** `.env` files, tokens and authorization codes are never read, shown or committed.\n"
        "- **Evals:** expected values are not edited to make checks pass."
    )
    st.caption("Descriptive page; contains no financial figures.")
