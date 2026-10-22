"""Close Review Workspace - entry point. Run: streamlit run 05_review_workspace/app/Home.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st  # noqa: E402

import data  # noqa: E402
import ui  # noqa: E402
from views import (analysis, architecture, datasources, demo_run, evaluations,  # noqa: E402
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


def _run_page(run_dir):
    def render():
        demo_run.render_run(run_dir)
    render.__name__ = run_dir.name  # url_path is set explicitly; the name only keeps pages distinct
    return st.Page(render, title=demo_run.label(run_dir), url_path=run_dir.name)


# One page per demo_runs/output_NNN folder, newest first. Re-read on every rerun, so new runs appear on refresh.
run_pages = [_run_page(d) for d in data.list_demo_runs()]
if not run_pages:
    run_pages = [st.Page(demo_run.render_empty, title="Demo runs", url_path="demo_runs")]
st.navigation({"Workspace": pages, "Demo runs": run_pages}).run()
