"""Which run is selected. Every client-data page starts with need_run(); with no runs it shows only the empty state."""
import streamlit as st

import data
import ui
from views import run_controls


def current_run():
    """The run chosen in the sidebar selector (key run_pick), else the newest run, else None."""
    runs = data.list_runs()
    pick = st.session_state.get("run_pick")
    return next((r for r in runs if r.name == pick), runs[0] if runs else None)


def need_run(title: str):
    run = current_run()
    if run is None:
        st.title(title)
        ui.no_runs()
        run_controls.render(None)
        return None
    ui.run_header(title, run)
    return run
