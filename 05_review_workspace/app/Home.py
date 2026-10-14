"""Close Review Workspace - entry point. Run: streamlit run 05_review_workspace/app/Home.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st  # noqa: E402

import data  # noqa: E402
import ui  # noqa: E402
from views import (analysis, architecture, datasources, evaluations,  # noqa: E402
                   insights, overview, runs)

st.set_page_config(page_title=ui.APP_NAME, page_icon=None, layout="wide")
ui.inject_css()

with st.sidebar:
    st.markdown(f"### {ui.APP_NAME}")
    clients = data.list_clients()
    client = st.selectbox("Client", clients, key="client") if clients else None
    periods = data.list_periods(client) if client else []
    period = st.selectbox("Period", periods, key="period") if periods else None
    if not clients:
        st.caption("No clients found in outputs/.")
    elif not periods:
        st.caption("No review packets for this client.")
    st.divider()

st.session_state["ctx"] = {"client": client, "period": period}

pages = [
    st.Page(overview.render, title="Overview", url_path="overview", default=True),
    st.Page(analysis.render, title="Financial Analysis", url_path="analysis"),
    st.Page(insights.render, title="Insights & Review", url_path="insights"),
    st.Page(datasources.render, title="Data Sources", url_path="sources"),
    st.Page(runs.render, title="Runs", url_path="runs"),
    st.Page(evaluations.render, title="Evaluations", url_path="evaluations"),
    st.Page(architecture.render, title="Architecture & Security", url_path="architecture"),
]
st.navigation(pages).run()
