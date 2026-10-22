"""One page per run folder (runs/runN/). Reads files only: nothing here calculates a figure or imports the engine."""
import json
import re

import pandas as pd
import streamlit as st

import ui
from views._ctx import need_run

STATEMENT = re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*$")
FAIL_BANNER = "Code grader failed: not ready for sign-off"
BADGE = {"PASS": ":green[**PASS**]", "FAIL": ":red[**FAIL**]", "NOT_RUN": ":gray[**NOT RUN**]"}


def _nf(rel):
    """The run does not contain this file. Shown as missing; never borrowed from elsewhere."""
    ui.missing_name(rel)


def _src(run, rel):
    ui.source_note(f"{run['dir'].name}/{rel}")


def _verdict(v):
    return v if v else "not recorded"


def _json(obj):
    """st.json with credential-looking strings withheld, like every other page."""
    st.json(json.loads(ui.scrub(json.dumps(obj))))


def _md(text):
    st.markdown(ui.scrub(text).replace("$", "\\$"))  # $ would start LaTeX


def _grade_state(run):
    """(passed|None, numbers, mismatches) for the final grade: run.json first, then the grade file."""
    r = run["run"].data if run["run"].ok else {}
    fg = r.get("final_grade") or (run["final_grade"].data if run["final_grade"].ok else None)
    if not fg:
        return None, None, []
    return fg.get("passed"), fg.get("numbers"), fg.get("mismatches") or []


def _summary(run):
    st.header("1. Summary")
    sm = run["summary"]
    if sm.ok:
        _md(sm.data)
        _src(run, run["files"]["summary"])
    else:
        _nf(run["files"]["summary"])


def _headline(run):
    st.header("2. Headline numbers")
    p = run["packet"]
    if not p.ok:
        return _nf(run["files"]["packet"])
    m = p.data.get("months", {}).get(run["month"], {})
    gp = m.get("gross_profit", {})
    cash = p.data.get("cash") or {}
    win = cash.get("primary_window")
    rw = cash.get("runway_months") or {}
    rev, opex, ni = m.get("revenue", {}), m.get("operating_expenses", {}), m.get("net_income", {})
    c = st.columns(3)
    c[0].metric("Revenue", ui.money(rev.get("value")), ui.delta(rev.get("mom_change"), rev.get("mom_pct")))
    c[1].metric("Gross margin", ui.pct(gp.get("margin")), ui.pp(gp.get("margin_change_pp")))
    c[2].metric("OPEX", ui.money(opex.get("value")), ui.delta(opex.get("mom_change"), opex.get("mom_pct")), delta_color="inverse")
    c = st.columns(3)
    c[0].metric("Net income", ui.money(ni.get("value")), ui.delta(ni.get("mom_change"), ni.get("mom_pct")))
    c[1].metric("Cash", ui.money(cash.get("value")) if cash else "n/a",
                ui.delta(cash.get("mom_change"), cash.get("mom_pct")) if cash else None)
    c[2].metric(f"Runway ({win} burn)" if win else "Runway", f"{rw[win]:.1f} months" if win in rw else "n/a")
    _src(run, run["files"]["packet"])


def _notes(review):
    """{statement number: (status, note)} from a reviewer JSON; falls back to its `changes` list."""
    out = {}
    if not review.ok:
        return out
    for n in review.data.get("statement_notes") or []:
        out[n.get("statement")] = (n.get("status"), n.get("note") or "")
    for ch in review.data.get("changes") or []:
        out[ch.get("statement")] = ("change", ch.get("issue") or "")
    return out


def _statements(loaded):
    """{number: text} of the numbered statements in a commentary file."""
    out = {}
    if loaded.ok:
        for line in loaded.data.splitlines():
            m = STATEMENT.match(line)
            if m:
                out[int(m.group(1))] = m.group(2)
    return out


def _commentary_table(run, r):
    st.header("3. Commentary review (draft vs final)")
    nr = run["run_obj"].not_run("03_commentary")
    if nr:
        st.info(nr.strip())
        return _src(run, "03_commentary/NOT_RUN.md")
    final, draft = _statements(run["commentary"]), _statements(run["commentary_draft"])
    if not run["commentary"].ok:
        return _nf(run["files"]["commentary"])
    st.caption("Statement text is written by Claude, graded by code. Shown verbatim from the commentary files.")
    first, last = _notes(run["review_first"]), _notes(run["review"])
    rows = []
    for n, text in final.items():
        f1, f2 = first.get(n), last.get(n)
        d = draft.get(n)
        rows.append({"#": n, "Draft": d if d is not None else "-", "Final": text,
                     "Changed": "yes" if d is not None and d != text else "",
                     "First review": f1[0] if f1 else "-", "Final review": f2[0] if f2 else "-",
                     "Reviewer note": (f2 or f1 or ("", ""))[1], "Flag": "change requested" if f1 and f1[0] == "change" else ""})
    c = st.columns(2)
    c[0].metric("First reviewer verdict", _verdict(r.get("reviewer_first_verdict")))
    c[1].metric("Final reviewer verdict", _verdict(r.get("reviewer_final_verdict")))
    if not rows:
        st.caption("No numbered statements found in the commentary file.")
    else:
        df = pd.DataFrame(rows)
        st.dataframe(df.style.apply(lambda row: ["background-color: #FBE3D6" if row["Flag"] else "" for _ in row], axis=1),
                     width="stretch", hide_index=True)
    if not run["review"].ok:
        st.caption(f"Reviewer columns empty: {run['files']['review']} was not produced in this run.")
    for k in ("commentary_draft", "commentary", "review_first", "review"):
        _src(run, run["files"][k])


def _grade_history(run, r, passed, numbers, mismatches):
    st.header("4. Grade history")
    if run["run_obj"].not_run("03_commentary"):
        return st.caption("Claude stages were not run for this run; nothing was graded.")
    attempts = r.get("grade_attempts") or (run["grade_record"].data.get("attempts") if run["grade_record"].ok else None)
    if attempts:
        ui.table([{"Attempt": i, "Result": "PASS" if a.get("passed") else "FAIL", "Numbers matched": a.get("numbers"),
                   "Mismatches": len(a.get("mismatches") or []), "Detail": "; ".join(a.get("mismatches") or [])}
                  for i, a in enumerate(attempts, 1)])
        st.markdown(f"Retry used: **{'yes' if r.get('retry_used') else 'no' if r.get('retry_used') is not None else 'n/a'}**")
    else:
        st.caption("No grade attempts recorded.")
    if passed is None:
        st.warning("No final grade recorded for this run.")
    else:
        st.markdown(f"**Final grade: {'PASS' if passed else 'FAIL'}** — numbers matched {numbers}; mismatches {len(mismatches)}")
        for m_ in mismatches:
            st.write(f"- {m_}")
    _src(run, run["files"]["grade_record"])
    _src(run, run["files"]["final_grade"])


def _scores(run):
    st.header("5. Reviewer scores and open questions")
    nr = run["run_obj"].not_run("04_review")
    if nr:
        st.info(nr.strip())
        return _src(run, "04_review/NOT_RUN.md")
    rv = run["review"]
    if not rv.ok:
        return _nf(run["files"]["review"])
    scores = rv.data.get("scores") or {}
    c = st.columns(4)
    for col, key in zip(c, ("numbers", "coverage", "causes", "tone")):
        s = scores.get(key) or {}
        col.metric(key.title(), f"{s['ok']} / {s['of']}" if "ok" in s and "of" in s else "n/a")
    qs = rv.data.get("open_questions") or []
    st.markdown(f"**Open questions ({len(qs)})**")
    if not qs:
        st.caption("None.")
    for q in qs:
        st.markdown(f"- {q.get('question', '')}" + (f"  \n  *Why:* {q['why']}" if q.get("why") else ""))
    _src(run, run["files"]["review"])


def _evals(run):
    st.header("6. Evals for this run")
    es = run["evals_summary"]
    if not es.ok:
        return _nf(run["files"]["evals_summary"])
    rows = []
    for key, label, fkey in (("golden", "Golden evals", "golden"), ("commentary_grade", "Commentary grade", "grade_report"),
                             ("flawed_control", "Flawed control (must FAIL)", "flawed"), ("workbook_hash", "Workbook hash before = after", "hash"),
                             ("regress_fast", "regress --fast", "regress")):
        e = es.data.get(key)
        if e:
            rows.append((label, e.get("status", "NOT_RUN"), e.get("detail", ""), fkey))
    for label, status, detail, fkey in rows:
        c = st.columns([2, 1, 4])
        c[0].markdown(f"**{label}**")
        c[1].markdown(BADGE.get(status, status))
        c[2].caption(detail)
    for label, status, _, fkey in rows:
        with st.expander(f"{label}: {run['files'][fkey]}"):
            loaded = run.get(fkey)
            if status == "NOT_RUN":
                st.caption("Not run in this run.")
            elif loaded is not None and loaded.ok:
                st.code(ui.scrub(loaded.data)[-6000:], language=None)
                _src(run, run["files"][fkey])
            else:
                _nf(run["files"][fkey])
    st.markdown(f"Overall: {BADGE.get(es.data.get('overall'), es.data.get('overall'))}")
    _src(run, run["files"]["evals_summary"])


def _movements(run):
    st.header("7. Flux and top movements")
    p, fx = run["packet"], run["flux"]
    if p.ok:
        mv = p.data.get("top_movements") or []
        st.markdown("**Top movements (month over month)**")
        ui.table([{"Account": x.get("account"), "Change": ui.money2(x.get("mom_change"))} for x in mv]) if mv else st.caption("None.")
        _src(run, run["files"]["packet"])
    else:
        _nf(run["files"]["packet"])
    if fx.ok:
        items = fx.data.get("items") or []
        st.markdown(f"**Flux items ({len(items)})**")
        ui.table([{"Account": i.get("account"), "Section": i.get("section"), "Reason": i.get("reason_code"),
                   "Severity": i.get("severity"), "Current": ui.money2(i.get("current")), "Prior": ui.money2(i.get("prior")),
                   "Change": ui.money2(i.get("dollar_change")), "Change %": ui.pct(i.get("pct_change")),
                   "Source cell": i.get("source_cell_current")} for i in items]) if items else st.caption("None flagged.")
        _src(run, run["files"]["flux"])
    else:
        _nf(run["files"]["flux"])


def _memo(run):
    st.header("8. Owner memo")
    nr = run["run_obj"].not_run("06_pack")
    if nr:
        st.info(nr.strip())
        return _src(run, "06_pack/NOT_RUN.md")
    if run["memo"].ok:
        _md(run["memo"].data)
        _src(run, run["files"]["memo"])
    else:
        _nf(run["files"]["memo"])


def _raw(run):
    st.header("9. Raw JSON")
    found = run["run_obj"].all_json()
    for loaded in found:
        with st.expander(loaded.path):
            _json(loaded.data)
            ui.source_note(loaded.path)
    if not found:
        _nf("run.json")


def _download(run):
    st.header("10. Excel downloads")
    files = run["run_obj"].excel_files()
    for p in files:
        st.download_button(f"Download {p.parent.name}/{p.name}", data=p.read_bytes(), file_name=p.name,
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"dl-{run['dir'].name}-{p.parent.name}-{p.name}")
        _src(run, f"{p.parent.name}/{p.name}")
    if not any(p.parent.name == "06_pack" for p in files):
        _nf(run["files"]["pack"])


def render_body(run_obj):
    """Every section for one run, in a fixed order. Used by the Runs page and the Run detail page."""
    run = run_obj.bundle()
    r = run["run"].data if run["run"].ok else {}
    passed, numbers, mismatches = _grade_state(run)
    if passed is False:
        st.error(FAIL_BANNER)
    if run_obj.failed():
        st.error("This run FAILED: " + ("; ".join(r.get("errors") or []) or "see logs/pipeline.log") + f" (kept in {run_obj.folder})")
    if run["missing"] and (run_obj.kind() == "Full (Claude)" or not run["run"].ok):
        st.warning("Not produced in this run: " + ", ".join(run["missing"]))
    if not run["run"].ok:
        _nf("run.json")
    _summary(run)
    _headline(run)
    _commentary_table(run, r)
    _grade_history(run, r, passed, numbers, mismatches)
    _scores(run)
    _evals(run)
    _movements(run)
    _memo(run)
    _raw(run)
    _download(run)


def render():
    run = need_run("Run detail")
    if run:
        st.caption("Read from the run folder only; nothing on this page is calculated.")
        render_body(run)
