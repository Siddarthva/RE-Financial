import streamlit as st

import actions
import data
import ui
from views._ctx import need_client


def _tile(col, label, passed, total):
    if total is None:
        col.metric(label, "n/a")
    else:
        col.metric(label, f"{passed}/{total}", "All passing" if passed == total else f"{total - passed} failing",
                   delta_color="normal" if passed == total else "inverse")


def _golden(g):
    st.subheader("Golden cases")
    cases = g.get("cases", [])
    kinds = ["workbook", "perturbed", "synthetic"]
    f = st.columns([2, 1])
    srcs = f[0].multiselect("Source", kinds, default=kinds, key="ev_src")
    res = f[1].selectbox("Result", ["All", "Pass", "Fail"], key="ev_res")
    if "synthetic" in srcs and not any(c.get("source") == "synthetic" for c in cases):
        st.caption("No synthetic golden cases exist in evals/golden_cases.json.")
    shown = [c for c in cases if c.get("source") in srcs and (res == "All" or c.get("passed") == (res == "Pass"))]
    if not shown:
        return st.caption("No cases match the filters.")
    sel = st.dataframe([{"ID": c["id"], "Case": c["name"], "Source": c["source"],
                         "Result": "Pass" if c["passed"] else "Fail"} for c in shown],
                       width="stretch", hide_index=True, on_select="rerun", selection_mode="single-row", key="ev_sel")
    rows = sel.selection.rows if sel and sel.selection else []
    if not rows:
        return st.caption("Select a case to see its input, expected vs actual, and tolerance.")
    c = shown[rows[0]]
    (st.success if c["passed"] else st.error)(f"{c['id']} {c['name']}: {'PASS' if c['passed'] else 'FAIL'}")
    st.markdown("**Input**")
    st.json(c.get("input") or {}, expanded=False)
    if c.get("perturbation"):
        st.caption(f"Perturbation: {c['perturbation']}")
    k = st.columns(2)
    k[0].markdown("**Expected**")
    k[0].json(c.get("expected") or {}, expanded=True)
    k[1].markdown("**Actual (from the run)**")
    k[1].code(c.get("actual") or "n/a", language=None)
    st.markdown(f"**Tolerance / grading:** {c.get('tolerance') or 'n/a'}")


def _mutation(m):
    st.subheader("Mutation test")
    if not m:
        return ui.empty_state("mutation results", "outputs/mutation_report.md")
    ui.table([{"Mutation": r["mutation"], "Module": r["module"], "Caught": "Yes" if r["caught"] else "No - gap",
               "Caught by": ", ".join(r["caught_by"]) or "-"} for r in m["rows"]])
    ui.source_note(m["source"])


def render():
    client = need_client()
    if not client:
        return
    ui.title("Evaluations", "Deterministic checks on the engine and the commentary")
    if st.button("Run golden evals", type="primary",
                 help="Runs scripts/export_eval_results.py, which runs evals/run_golden_evals.py unchanged."):
        with st.spinner("Running golden evals..."):
            ok, out = actions.run_golden_evals()
        if ok:
            st.rerun()
        st.error("Golden evals did not complete.")
        if out:
            st.code(ui.scrub(out), language=None)

    r = data.load_eval_summary()
    cg = data.load_commentary_grade()
    if not r.ok:
        ui.empty_state("eval results", r.path, "Press 'Run golden evals' to generate it. " + r.error)
    d = r.data or {}
    u, g, m = d.get("unit"), d.get("golden"), d.get("mutation")
    t = st.columns(4)
    _tile(t[0], "Unit tests", u and u["passed"], u and u["total"])
    _tile(t[1], "Golden cases", g and g["passed"], g and g["total"])
    _tile(t[2], "Mutants caught", m and m["caught"], m and m["total"])
    if cg.ok:
        _tile(t[3], "Commentary numbers", cg.data.get("numbers_matched"), cg.data.get("numbers_checked"))
    else:
        _tile(t[3], "Commentary numbers", None, None)
    if r.ok:
        st.caption(f"Golden run exported {d.get('generated_at')}. Unit-test counts come from {u['source'] if u else 'n/a'} "
                   "and are not re-run by the button. Commentary: outputs/commentary_grade.json.")
        _golden(g)
        _mutation(m)
    if cg.ok:
        st.subheader("Commentary grade")
        ui.table([{"Number": n.get("token"), "Kind": n.get("kind"), "Fact": n.get("fact"), "Matched": n.get("matched")}
                  for n in cg.data.get("numbers", [])])
        ui.source_note(cg.path)
