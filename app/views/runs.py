import pandas as pd
import streamlit as st

import actions
import data
import ui
from views._ctx import ctx, need_client

STAGES = ["Intake", "Calculate", "Skill draft", "Review", "Package", "Approved"]


def _seconds(v):
    return "n/a" if v is None else f"{v:.2f}s"


def _timeline(client, period, manifest, latest):
    by_name = {s.get("name"): s for s in manifest.get("stages", [])}
    down = data.downstream_status(client, period) if latest else {}
    rows = []
    for name in STAGES:
        if name in by_name:
            s = by_name[name]
            rows.append({"Stage": name, "Status": s.get("status"), "Duration": _seconds(s.get("duration_s")),
                         "Source": "manifest"})
        elif name in down:
            rows.append({"Stage": name, "Status": down[name]["status"], "Duration": "n/a", "Source": down[name]["file"]})
        else:
            rows.append({"Stage": name, "Status": "not recorded", "Duration": "n/a", "Source": "-"})
    extra = [s for n, s in by_name.items() if n not in STAGES]
    for s in extra:
        rows.append({"Stage": s.get("name"), "Status": s.get("status"), "Duration": _seconds(s.get("duration_s")), "Source": "manifest"})
    ui.table(rows)
    if not latest:
        st.caption("Skill draft, Review, Package and Approved are shown for the latest run of a period only (they read current files).")


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


def render():
    client = need_client()
    if not client:
        return
    _, period = ctx()
    ui.title("Runs", f"{client} · period {period or 'n/a'}")

    ap = data.load_approval(client, period) if period else None
    locked = bool(ap and ap.ok and ap.data.get("status") == "approved")
    if period:
        if st.button("Run analysis", type="primary", disabled=locked,
                     help="Runs scripts/run_pipeline.py for the selected client and period."):
            with st.spinner("Running pipeline..."):
                ok, out = actions.run_analysis(client, period)
            (st.success if ok else st.error)("Pipeline finished." if ok else "Pipeline failed.")
            if out:
                st.code(ui.scrub(out), language=None)
        if locked:
            st.caption("This period is approved and locked; the pipeline will not re-run it.")

    m = data.load_manifests(client)
    if not m.ok:
        ui.empty_state("run manifests", m.path, m.error)
    else:
        runs = sorted((i["content"] for i in m.data), key=lambda c: c.get("started_at", ""), reverse=True)
        ui.table([{"Run ID": r.get("run_id"), "Started": r.get("started_at"), "Period": r.get("period"),
                   "Source": (r.get("source") or {}).get("workbook"), "Skill version": r.get("skill_version"),
                   "Git SHA": r.get("git_sha") or "n/a", "Status": r.get("status")} for r in runs])
        ui.source_note(m.path)
        ids = [r.get("run_id") for r in runs]
        pick = st.selectbox("Run", ids, key="run_pick")
        run = next(r for r in runs if r.get("run_id") == pick)
        st.subheader("Stage timeline")
        newest_for_period = max((r.get("started_at", "") for r in runs if r.get("period") == run.get("period")), default="")
        _timeline(client, run.get("period"), run, run.get("started_at") == newest_for_period)
        _diff(run)

    st.subheader("Audit log")
    a = data.load_audit_log(client)
    if a.ok:
        ui.table(pd.DataFrame(a.data))
        ui.source_note(a.path)
    else:
        ui.empty_state("audit log", a.path, a.error)
