import pandas as pd
import streamlit as st

import actions
import data
import ui
from views import demo_run
from views._ctx import ctx, need_client

NO_CLAUDE = "Claude stages were not run for this run. Use 'Run full analysis with Claude' or /demo-run."
HINT = "To run the full analysis with Claude, type /demo-run <client> <YYYY-MM> in Claude Code (the claude CLI was not found on PATH)."
TIMEOUT_MSG = "Claude did not finish within 10 minutes and was stopped. Check demo_runs/ for a partial run folder, or run /demo-run in Claude Code."


def _seconds(v):
    return "n/a" if v is None else f"{v:.1f}s"


def _timeline(row):
    rows = [{"Stage": r["Stage"], "Status": r["Status"], "Started (IST)": r["Started (IST)"], "Duration": _seconds(r["duration_s"])}
            for r in data.run_timeline(row)]
    ui.table(rows)


def _diff(manifest):
    d = manifest.get("diff_vs_previous")
    st.markdown("**v1 vs v2**")
    if not d:
        return st.caption("No earlier run of this period to compare against.")
    changed = d.get("changed") or []
    if not changed:
        return st.caption(f"Identical to {d.get('previous_run_id')}: no differences in the review packet.")
    st.caption(f"Compared with {d.get('previous_run_id')}: {len(changed)} differing values.")
    ui.table([{"Path": c.get("path"), "v1": str(c.get("old")), "v2": str(c.get("new"))} for c in changed])


def _claude_button(client, period):
    exe = actions.claude_path()
    if not exe:
        return st.caption(HINT)
    if not st.button("Run full analysis with Claude", disabled=not period,
                     help="Runs: claude -p \"/demo-run <client> <period>\" with the allowed tools of .claude/commands/demo-run.md. "
                          "Takes a few minutes; the run appears below as its own Output NNN."):
        return
    before = {p.name for p in data.list_demo_runs()}
    with st.expander("Live log", expanded=True):
        box = st.empty()
        with st.spinner("Claude is running /demo-run (up to 10 minutes)..."):
            status, log = actions.run_claude(client, period, on_line=lambda t: box.code(ui.scrub(t[-4000:]), language=None))
    new = [p for p in data.list_demo_runs() if p.name not in before]
    if new:
        st.session_state["run_pick"] = f"demo:{new[0].name}"
    st.session_state["claude_result"] = {"status": status, "log": ui.scrub(log)[-6000:], "new": new[0].name if new else None}
    st.rerun()


def _claude_result():
    res = st.session_state.pop("claude_result", None)
    if not res:
        return
    if res["status"] == "ok":
        st.success(f"Claude finished. Showing {res['new']}." if res["new"] else "Claude finished, but no new demo run folder appeared.")
    elif res["status"] == "timeout":
        st.error(TIMEOUT_MSG)
    else:
        st.error("Claude run failed." if res["status"] == "failed" else "Claude run could not start.")
    if res["log"]:
        with st.expander("Claude log"):
            st.code(res["log"], language=None)


def _pipeline_detail(client, row):
    st.warning(NO_CLAUDE)
    packet = data.load_packet(client, row["period"])
    with st.expander("Review packet JSON", expanded=True):
        if packet.ok:
            st.caption("Run-level packet file for this period; each run of the period overwrites it, so an older run shows the latest packet.")
            demo_run._json(packet.data)
            ui.source_note(packet.path)
        else:
            ui.empty_state("review packet", packet.path, packet.error)
    _diff(row["content"])


def render():
    client = need_client()
    if not client:
        return
    _, period = ctx()
    ui.title("Runs", f"{client} · period {period or 'n/a'}")

    ap = data.load_approval(client, period) if period else None
    locked = bool(ap and ap.ok and ap.data.get("status") == "approved")
    if period:
        if st.button("Run pipeline only (no Claude)", type="primary", disabled=locked,
                     help="Runs scripts/run_pipeline.py for the selected client and period. No Claude stages."):
            with st.spinner("Running pipeline..."):
                ok, out = actions.run_analysis(client, period)
            (st.success if ok else st.error)("Pipeline finished." if ok else "Pipeline failed.")
            if out:
                st.code(ui.scrub(out), language=None)
        if locked:
            st.caption("This period is approved and locked; the pipeline will not re-run it.")
    _claude_button(client, period)
    _claude_result()

    runs = data.list_all_runs(client)
    if not runs:
        ui.empty_state("runs", f"outputs/{client}/manifest*.json or demo_runs/output_NNN/run.json", "No runs yet")
    else:
        ui.table([{"Run": r["run"], "Type": r["kind"], "Started (IST)": r["started"], "Period": r["period"],
                   "Final grade": r["final_grade"], "Reviewer verdict": r["verdict"], "Git SHA": r["sha"], "Status": r["status"]}
                  for r in runs])
        ui.source_note(f"outputs/{client}/manifest*.json and demo_runs/output_NNN/run.json")
        by_key = {r["key"]: r for r in runs}
        if st.session_state.get("run_pick") not in by_key:
            st.session_state.pop("run_pick", None)
        pick = st.selectbox("Run", list(by_key), key="run_pick", format_func=lambda k: f"{by_key[k]['run']} · {by_key[k]['kind']}")
        row = by_key[pick]
        st.subheader("Stage timeline")
        _timeline(row)
        if row["kind"] == data.FULL:
            demo_run.render_body(row["dir"])
        else:
            _pipeline_detail(client, row)

    st.subheader("Audit log")
    a = data.load_audit_log(client)
    if a.ok:
        ui.table(pd.DataFrame(a.data))
        ui.source_note(a.path)
    else:
        ui.empty_state("audit log", a.path, a.error)
