"""Close Review Workspace - entry point. Run: streamlit run 05_review_workspace/app/Home.py

Client-data pages show only what is inside the run chosen in the sidebar (runs/runN/). The two project pages
(Evaluations, Architecture & Security) are listed separately and are not run data."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st  # noqa: E402

import data  # noqa: E402
import ui  # noqa: E402
from views import (analysis, architecture, datasources, run_detail, evaluations,  # noqa: E402
                   insights, overview, runs)

st.set_page_config(page_title=ui.APP_NAME, page_icon=None, layout="wide")
ui.inject_css()

with st.sidebar:
    st.markdown(f"### {ui.APP_NAME}")
    found = {r.name: r for r in data.list_runs()}  # newest first; re-read on every rerun, so new runs appear on refresh
    nxt = st.session_state.pop("run_pick_next", None)  # set by the run buttons: switch to the run they just created
    if nxt in found:
        st.session_state["run_pick"] = nxt
    if found:
        if st.session_state.get("run_pick") not in found:
            st.session_state.pop("run_pick", None)
        st.selectbox("Run", list(found), key="run_pick", format_func=lambda n: found[n].label())
    else:
        st.caption("No runs yet.")
    st.divider()

st.navigation({
    "Run data": [
        st.Page(overview.render, title="Overview", url_path="overview", default=True),
        st.Page(analysis.render, title="Financial Analysis", url_path="analysis"),
        st.Page(insights.render, title="Insights & Review", url_path="insights"),
        st.Page(datasources.render, title="Data Sources", url_path="sources"),
        st.Page(runs.render, title="Runs", url_path="runs"),
        st.Page(run_detail.render, title="Run detail", url_path="run_detail"),
    ],
    "Project (not run data)": [
        st.Page(evaluations.render, title="Evaluations", url_path="evaluations"),
        st.Page(architecture.render, title="Architecture & Security", url_path="architecture"),
    ],
}).run()
