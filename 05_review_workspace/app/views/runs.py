import pandas as pd
import streamlit as st

import data
import ui
from views import run_controls, run_detail
from views._ctx import current_run, need_run

def _seconds(v):
    return "n/a" if v is None else f"{v:.1f}s"


def render():
    runs = data.list_runs()
    if not runs:
        run = need_run("Runs")  # empty state + run buttons
        return
    run = current_run()
    ui.run_header("Runs", run)
    run_controls.render(run)

    rows = [data.run_row(r) for r in runs]
    ui.table([{"Run": x["run"], "Type": x["kind"], "Started (IST)": x["started"], "Client": x["client"], "Period": x["period"],
               "Final grade": x["final_grade"], "Reviewer verdict": x["verdict"], "Git SHA": x["sha"], "Status": x["status"]}
              for x in rows])
    ui.source_note("runs/runN/run.json (one per run)")

    st.subheader(f"Stage timeline: Run {run.number}")
    ui.table([{"Stage": r["Stage"], "Status": r["Status"], "Started (IST)": r["Started (IST)"], "Duration": _seconds(r["duration_s"])}
              for r in data.run_timeline(run)])
    ui.source_note(run.run.path if run.run.ok else f"{run.name}/run.json")
    if not run.run.ok:
        ui.missing(run.run)

    run_detail.render_body(run)

    st.subheader("Audit log")
    a = run.json("audit_log")
    if a.ok:
        ui.table(pd.DataFrame(a.data))
        ui.source_note(a.path)
    else:
        ui.missing_name(run.filename("audit_log"))
