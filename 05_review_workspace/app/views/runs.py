import pandas as pd
import streamlit as st

import data
import ui
from views import demo_run, run_controls
from views._ctx import current_run, need_run

NO_CLAUDE = "Claude stages were not run for this run. Use 'Run full analysis with Claude' or /demo-run."


def _seconds(v):
    return "n/a" if v is None else f"{v:.1f}s"


def _diff(manifest):
    st.markdown("**v1 vs v2**")
    if not manifest.ok:
        return ui.missing(manifest)
    d = manifest.data.get("diff_vs_previous")
    if not d:
        st.caption("No earlier run of this period to compare against.")
    else:
        changed = d.get("changed") or []
        if not changed:
            st.caption(f"Identical to {d.get('previous_run_id')}: no differences in the review packet.")
        else:
            st.caption(f"Compared with {d.get('previous_run_id')}: {len(changed)} differing values.")
            ui.table([{"Path": c.get("path"), "v1": str(c.get("old")), "v2": str(c.get("new"))} for c in changed])
    ui.source_note(manifest.path)


def _pipeline_detail(run):
    st.warning(NO_CLAUDE)
    packet = run.json("packet")
    with st.expander("Review packet JSON", expanded=True):
        if packet.ok:
            demo_run._json(packet.data)
            ui.source_note(packet.path)
        else:
            ui.missing(packet)
    _diff(run.manifest())


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
    ui.source_note("demo_runs/output_NNN/run.json (one per run)")

    st.subheader(f"Stage timeline: Output {run.number}")
    ui.table([{"Stage": r["Stage"], "Status": r["Status"], "Started (IST)": r["Started (IST)"], "Duration": _seconds(r["duration_s"])}
              for r in data.run_timeline(run)])
    ui.source_note(run.run.path if run.run.ok else f"{run.name}/run.json")
    if not run.run.ok:
        ui.missing(run.run)

    if run.kind() == data.FULL:
        demo_run.render_body(run)
    else:
        _pipeline_detail(run)

    st.subheader("Audit log")
    a = run.json("audit_log")
    if a.ok:
        ui.table(pd.DataFrame(a.data))
        ui.source_note(a.path)
    else:
        ui.missing(a)
