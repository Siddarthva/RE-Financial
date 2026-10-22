"""Create the next numbered run folder runs/runN/ and fill it with everything that run produced.

    python scripts/new_run.py abc 2026-06                    # pipeline-only run: intake + calculate + golden evals + hash check
    python scripts/new_run.py abc 2026-06 --claude           # start of a full run: pipeline into runs/runN/_work, left open for /demo-run
    python scripts/new_run.py mark runs/run3 "Skill draft" start   # also: end [--status X], skipped
    python scripts/new_run.py finish runs/run3 [--with-regress]    # full run: move the work files into the layout, run the evals, write SUMMARY.md
    python scripts/new_run.py finish runs/run3 --failed "reason"   # keep the folder, record status "failed"

`new_run` never writes to outputs/ and never touches another run. The number is the highest existing runN + 1 and is never
reused. A run folder is never deleted: a failed stage leaves the folder with status "failed", the error and the log.
Layout of runs/runN/ (see runs/README.md): SUMMARY.md, run.json, 01_intake, 02_numbers, 03_commentary, 04_review, 05_evals,
06_pack, logs. The engine scripts write into runs/runN/_work/<client>/; `finish` MOVES those files into the layout and
removes the then-empty _work. Nothing here approves anything.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

import run_client  # noqa: E402

RUNS = PROJECT / "runs"
IST = timezone(timedelta(hours=5, minutes=30))
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
FOLDER = re.compile(r"^run(\d+)$")
STAGE = re.compile(r"^(Skill draft|Review \((first|final)\)|Revise|Final grade|Package|Grade attempt [1-9]\d*)$")
WORK = "_work"
WORKBOOK = PROJECT / "data" / "ABC Inc - Financial Statements.xlsx"
WORKBOOK_SHA16 = "75da8d679a89551f"
GOLDEN = PROJECT / "03_evals" / "run_golden_evals.py"      # tests may point these at stubs
GRADER = PROJECT / "03_evals" / "grade_commentary.py"
REGRESS = PROJECT / "scripts" / "regress.py"
FLAWED_CONTROL = PROJECT / "outputs" / "abc" / "commentary_{m}_flawed_control.md"
REGRESS_RESULTS = PROJECT / "outputs" / "regress_results.json"
SECTIONS = ("01_intake", "02_numbers", "03_commentary", "04_review", "05_evals", "06_pack", "logs")
FULL, PIPE = "Full (Claude)", "Pipeline only"
NOT_RUN = "Claude stages were not run for this run.\n"


def stamps(t: datetime) -> dict:
    return {"utc": t.astimezone(timezone.utc).isoformat(timespec="seconds"), "ist": t.astimezone(IST).isoformat(timespec="seconds")}


def _git(*args: str) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=PROJECT, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def sha256_of(p: Path) -> str | None:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return None


def validate(client: str, month: str, clients_root: Path = run_client.CLIENTS_ROOT) -> str | None:
    """An error message, or None. Runs before any folder is made."""
    if not run_client.CLIENT_ID.match(client):
        return f"invalid client id {client!r}; use lowercase letters, digits, '-' or '_' (e.g. abc)."
    if not MONTH.match(month):
        return f"month must look like 2026-06, got {month!r}."
    if not (Path(clients_root) / client / "config.yaml").is_file():
        return f"unknown client {client!r}: no {Path(clients_root) / client / 'config.yaml'}."
    return None


def next_folder(root: Path) -> tuple[int, Path]:
    """Create root/runN with the next free number. mkdir without exist_ok makes overwriting impossible."""
    root.mkdir(parents=True, exist_ok=True)
    while True:
        n = max((int(m.group(1)) for p in root.iterdir() if (m := FOLDER.match(p.name))), default=0) + 1
        folder = root / f"run{n}"
        try:
            folder.mkdir()
            return n, folder
        except FileExistsError:
            continue


def read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_text(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return None


def write_run(folder: Path, run: dict) -> None:
    (folder / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")


def log(folder: Path, text: str) -> None:
    (folder / "logs").mkdir(exist_ok=True)
    with open(folder / "logs" / "pipeline.log", "a", encoding="utf-8") as f:
        f.write(text.rstrip("\n") + "\n")


def _py(args: list, timeout: int = 1800) -> tuple[int, str]:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    try:
        r = subprocess.run([sys.executable, *map(str, args)], cwd=PROJECT, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return 124, f"{Path(str(args[0])).name} did not finish within {timeout} seconds and was stopped."
    except OSError as exc:
        return 127, f"Could not start {args[0]}: {type(exc).__name__}"
    return r.returncode, r.stdout + (("\n" + r.stderr) if r.stderr.strip() else "")


def timed(run: dict, name: str, fn):
    """Run fn(); record start, end, duration and status of the stage in run['timings']. Errors are recorded, never raised."""
    t0 = datetime.now(timezone.utc)
    try:
        res, err = fn(), None
    except Exception as exc:  # the run folder must survive any stage failure
        res, err = None, f"{type(exc).__name__}: {exc}"
        run.setdefault("errors", []).append(f"{name}: {err}")
    t1 = datetime.now(timezone.utc)
    run.setdefault("timings", {})[name] = {"started": stamps(t0)["utc"], "ended": stamps(t1)["utc"],
                                           "duration_s": round((t1 - t0).total_seconds(), 1), "status": "failed" if err else "done"}
    return res


def create(client: str, month: str, root: Path = RUNS, clients_root: Path = run_client.CLIENTS_ROOT,
           claude: bool = False, with_regress: bool = False) -> tuple[int, Path]:
    err = validate(client, month, clients_root)
    if err:
        raise ValueError(err)
    started = datetime.now(timezone.utc)
    n, folder = next_folder(root)
    run = {"run_number": n, "run_id": folder.name, "client": client, "month": month, "mode": "claude" if claude else "pipeline_only",
           "kind": FULL if claude else PIPE, "status": "running", "started": stamps(started), "finished": None,
           "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"), "git_head": _git("rev-parse", "HEAD"),
           "workbook_sha256_before": sha256_of(WORKBOOK), "errors": [], "timings": {}, "stages": {}}
    write_run(folder, run)
    try:
        code, out = _py([PROJECT / "scripts" / "run_pipeline.py", client, month, "--clients-root", clients_root,
                         "--outputs-root", folder / WORK], timeout=900)
        log(folder, f"$ run_pipeline.py {client} {month}  (exit {code})\n{out}")
        work = folder / WORK / client
        manifests = sorted(work.glob(f"manifest_*-{client}-{month}.json"))
        manifest = read_json(manifests[-1]) if manifests else None
        run["pipeline_status"] = (manifest or {}).get("status", "failed")
        run["stages"] = {s["name"]: s["status"] for s in (manifest or {}).get("stages", [])}
        if "Grade commentary" in run["stages"] and not (work / f"commentary_{month}.md").is_file():
            run["stages"]["Grade commentary"] = "skipped (no draft yet)"
        for later in ("Commentary draft", "Review", "Package"):  # the Claude stages; `finish` overwrites these
            run["stages"].setdefault(later, "not run")
        t = started
        for s in (manifest or {}).get("stages", []):  # Intake and Calculate run back to back, so start = previous end
            if s.get("name") in ("Intake", "Calculate") and isinstance(s.get("duration_s"), (int, float)):
                end = t + timedelta(seconds=s["duration_s"])
                run["timings"][s["name"]] = {"started": stamps(t)["utc"], "ended": stamps(end)["utc"],
                                             "duration_s": round(s["duration_s"], 1), "status": s.get("status")}
                t = end
        failed = [f"{s['name']}: {s.get('error')}" for s in (manifest or {}).get("stages", []) if s.get("status") == "failed"]
        if code != 0 and not failed:
            failed = [f"pipeline exited {code}: {out.strip()[-300:]}"]
        run["errors"] += failed
    except Exception as exc:
        run["pipeline_status"] = "failed"
        run["errors"].append(f"pipeline: {type(exc).__name__}: {exc}")
    write_run(folder, run)
    if not claude:
        finalize(folder, with_regress=with_regress)
    return n, folder


def mark(folder: Path, stage: str, event: str, status: str | None = None) -> dict:
    """Record the start, end and duration of one stage in run.json. event: start, end or skipped."""
    if not STAGE.match(stage):
        raise ValueError(f"unknown stage {stage!r}")
    run = read_json(folder / "run.json")
    if not run:
        raise ValueError(f"{folder}/run.json is missing or unreadable")
    now = datetime.now(timezone.utc)
    e = run.setdefault("timings", {}).setdefault(stage, {})
    if event == "start":
        e.clear()
        e.update({"started": stamps(now)["utc"], "ended": None, "duration_s": None, "status": "running"})
    elif event == "end":
        began = e.get("started")
        if not began:
            raise ValueError(f"{stage!r} has no start; run `mark ... start` first")
        e.update({"ended": stamps(now)["utc"], "duration_s": round((now - datetime.fromisoformat(began)).total_seconds(), 1),
                  "status": status or "done"})
    elif event == "skipped":
        e.clear()
        e.update({"started": None, "ended": None, "duration_s": 0.0, "status": status or "skipped"})
    else:
        raise ValueError(f"unknown event {event!r}; use start, end or skipped")
    write_run(folder, run)
    return e


# ---- finish: move the work files into the layout, evals, SUMMARY.md ----
def _move(src: Path, dest_dir: Path, name: str | None = None) -> None:
    dest_dir.mkdir(exist_ok=True)
    shutil.move(str(src), str(dest_dir / (name or src.name)))


def organize(folder: Path, run: dict) -> None:
    """MOVE (not copy) the engine's working files from _work/<client>/ into the numbered sections."""
    client, m = run["client"], run["month"]
    work = folder / WORK / client
    for s in SECTIONS:
        (folder / s).mkdir(exist_ok=True)
    if work.is_dir():
        rules = [(f"intake_{m}.json", "01_intake", None),
                 (f"commentary_{m}_draft.md", "03_commentary", None), (f"commentary_{m}.md", "03_commentary", f"commentary_{m}_final.md"),
                 (f"commentary_grade_{m}.json", "03_commentary", None), (f"commentary_final_grade_{m}.json", "03_commentary", None),
                 (f"review_{m}_first.json", "04_review", None), (f"review_{m}.json", "04_review", f"review_{m}_final.json"),
                 (f"monthly_review_{m}.xlsx", "06_pack", None), (f"owner_memo_{m}.md", "06_pack", None), (f"approval_{m}.json", "06_pack", None)]
        for name, section, new in rules:
            if (work / name).is_file():
                _move(work / name, folder / section, new)
        for p in sorted(work.iterdir()):  # whatever else the engine produced (packet, flux, analysis.xlsx, manifests, ...)
            _move(p, folder / "02_numbers")
        work.rmdir()
    left = folder / WORK
    if left.is_dir():
        if any(left.iterdir()):
            raise RuntimeError(f"{WORK}/ is not empty after moving the files: {[p.name for p in left.iterdir()]}")
        left.rmdir()
    c03 = folder / "03_commentary"
    final, draft = c03 / f"commentary_{m}_final.md", c03 / f"commentary_{m}_draft.md"
    if final.is_file() and not draft.is_file():
        shutil.copyfile(final, draft)  # never revised after the first draft: the draft is the final text
        run["draft_equals_final"] = True
    if run["mode"] != "claude":
        for s in ("03_commentary", "04_review", "06_pack"):
            (folder / s / "NOT_RUN.md").write_text(NOT_RUN, encoding="utf-8")


def _grade(path: Path, out: Path) -> tuple[bool, str]:
    """grade_commentary.py on one commentary file; its side files go to a throw-away folder, never to outputs/."""
    with tempfile.TemporaryDirectory() as tmp:
        code, text = _py([GRADER, "--commentary", path, "--outputs-dir", tmp], timeout=300)
    out.write_text(text, encoding="utf-8")
    res = re.findall(r"RESULT:\s*(\w+)", text)
    return code == 0 and res[-1:] == ["PASS"], text


def run_evals(folder: Path, run: dict) -> dict:
    ev, m, client = folder / "05_evals", run["month"], run["client"]
    ev.mkdir(exist_ok=True)
    summary = {}
    code, text = _py([GOLDEN], timeout=900)
    (ev / "golden_results.txt").write_text(text, encoding="utf-8")
    score = re.findall(r"Score:\s*(\d+/\d+)", text)
    summary["golden"] = {"status": "PASS" if code == 0 and score else "FAIL", "detail": f"score {score[-1]}" if score else f"exit {code}, no score line",
                         "file": "golden_results.txt"}
    final = folder / "03_commentary" / f"commentary_{m}_final.md"
    if run["mode"] == "claude" and final.is_file():
        ok, _ = _grade(final, ev / "commentary_grade_report.txt")
        summary["commentary_grade"] = {"status": "PASS" if ok else "FAIL", "detail": "grade_commentary.py on this run's final commentary",
                                       "file": "commentary_grade_report.txt"}
        ctl = Path(str(FLAWED_CONTROL).format(m=m))
        if client == "abc" and ctl.is_file():
            ok, _ = _grade(ctl, ev / "flawed_control_check.txt")
            summary["flawed_control"] = {"status": "PASS" if not ok else "FAIL",
                                         "detail": "grader FAILED the flawed control, as required" if not ok else "grader PASSED the flawed control: the grader is broken",
                                         "file": "flawed_control_check.txt"}
        else:
            summary["flawed_control"] = {"status": "NOT_RUN", "detail": "no flawed control for this client and month", "file": None}
    else:
        why = "Claude stages were not run" if run["mode"] != "claude" else "no final commentary was produced"
        summary["commentary_grade"] = {"status": "NOT_RUN", "detail": why, "file": None}
        summary["flawed_control"] = {"status": "NOT_RUN", "detail": why, "file": None}
    after = sha256_of(WORKBOOK)
    before = run.get("workbook_sha256_before")
    match = bool(before) and before == after
    (ev / "workbook_hash.txt").write_text(f"before: {before}\nafter:  {after}\nmatch:  {'yes' if match else 'NO'}\n"
                                          f"recorded prefix {WORKBOOK_SHA16}: {'yes' if (after or '').startswith(WORKBOOK_SHA16) else 'NO'}\n", encoding="utf-8")
    run["workbook_sha256_after"], run["workbook_sha256_16"] = after, (after or "")[:16] or None
    summary["workbook_hash"] = {"status": "PASS" if match and (after or "").startswith(WORKBOOK_SHA16) else "FAIL",
                                "detail": f"before = after = {(after or '')[:16]}" if match else "hash changed or unreadable", "file": "workbook_hash.txt"}
    summary["overall"] = "FAIL" if any(v["status"] == "FAIL" for v in summary.values() if isinstance(v, dict)) else "PASS"
    (ev / "evals_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def run_regress(folder: Path) -> dict:
    """python scripts/regress.py --fast (about 9 min) into 05_evals/regress_fast.json; outputs/regress_results.json is restored afterwards."""
    before = REGRESS_RESULTS.read_bytes() if REGRESS_RESULTS.is_file() else None
    try:
        code, text = _py([REGRESS, "--fast"], timeout=3000)
        res = read_json(REGRESS_RESULTS)
    finally:
        if before is not None:
            REGRESS_RESULTS.write_bytes(before)
    rec = {"command": "python scripts/regress.py --fast", "exit_code": code, "held": code == 0, "output": text[-20000:], "results": res}
    (folder / "05_evals" / "regress_fast.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return rec


def _fill_from_files(folder: Path, run: dict) -> None:
    m = run["month"]
    rec = read_json(folder / "03_commentary" / f"commentary_grade_{m}.json") or {}
    first = read_json(folder / "04_review" / f"review_{m}_first.json") or {}
    final = read_json(folder / "04_review" / f"review_{m}_final.json") or {}
    fg = read_json(folder / "03_commentary" / f"commentary_final_grade_{m}.json")
    pack = folder / "06_pack" / f"monthly_review_{m}.xlsx"
    run["grade_attempts"] = [{"attempt": i, "passed": a.get("passed"), "numbers": a.get("numbers"), "mismatches": a.get("mismatches", [])}
                             for i, a in enumerate(rec.get("attempts", []), 1)] or None
    run["retry_used"] = rec.get("retry_used")
    run["reviewer_first_verdict"], run["reviewer_final_verdict"] = first.get("verdict"), final.get("verdict")
    run["final_grade"] = {"passed": fg["passed"], "numbers": fg["numbers"], "mismatches": fg["mismatches"]} if fg else None
    run["pack_path"] = pack.relative_to(folder).as_posix() if pack.is_file() else None
    run["open_question_count"] = len(final["open_questions"]) if isinstance(final.get("open_questions"), list) else None
    st = run.setdefault("stages", {})
    st["Commentary draft"] = "done" if (folder / "03_commentary" / f"commentary_{m}_final.md").is_file() and run["mode"] == "claude" else "not run"
    st["Review"] = "done" if final else "not run"
    st["Package"] = "done" if pack.is_file() and (folder / "06_pack" / f"owner_memo_{m}.md").is_file() else "not run"
    tm = run.setdefault("timings", {})
    for i, a in enumerate(rec.get("attempts", []), 1):
        if f"Grade attempt {i}" in tm:
            tm[f"Grade attempt {i}"]["status"] = "PASS" if a.get("passed") else "FAIL"
    if "Final grade" in tm and fg:
        tm["Final grade"]["status"] = "PASS" if fg["passed"] else "FAIL"
    for key, v in (("Review (first)", first.get("verdict")), ("Review (final)", final.get("verdict"))):
        if key in tm and v:
            tm[key]["status"] = v
    if run["mode"] == "claude" and first.get("verdict") == "approve":
        tm.setdefault("Revise", {"started": None, "ended": None, "duration_s": 0.0, "status": "skipped (first review approved)"})
        tm.setdefault("Review (final)", {"started": None, "ended": None, "duration_s": 0.0, "status": "skipped (first review is final)"})


def _num(v, f="{:,.0f}"):
    return "n/a" if v is None else f.format(v)


def headline(packet: dict | None, month: str) -> dict:
    """Values copied from the packet; nothing is recomputed."""
    if not packet:
        return {}
    mm = (packet.get("months") or {}).get(month, {})
    cash = packet.get("cash") or {}
    win = cash.get("primary_window")
    return {"revenue": (mm.get("revenue") or {}).get("value"), "revenue_mom_pct": (mm.get("revenue") or {}).get("mom_pct"),
            "gross_margin": (mm.get("gross_profit") or {}).get("margin"),
            "operating_expenses": (mm.get("operating_expenses") or {}).get("value"),
            "net_income": (mm.get("net_income") or {}).get("value"),
            "cash": cash.get("value"), "runway_window": win, "runway_months": (cash.get("runway_months") or {}).get(win) if win else None}


def write_summary(folder: Path, run: dict) -> None:
    m, ev = run["month"], run.get("evals") or {}
    packet = read_json(folder / "02_numbers" / f"review_packet_{m}.json")
    run["headline"] = hl = headline(packet, m)
    final_text = read_text(folder / "03_commentary" / f"commentary_{m}_final.md")
    review = read_json(folder / "04_review" / f"review_{m}_final.json") or {}
    fg = run.get("final_grade")
    grade = "not graded" if not fg else "PASS" if fg.get("passed") else "FAIL"
    L = [f"# Run {run['run_number']} · {run['client']} {m}", "",
         f"- **Type:** {run['kind']} · **Status:** {run['status'].upper()}",
         f"- **Date/time (IST):** {run['started']['ist'].replace('T', ' ')[:19]}  ·  duration {run.get('duration_s', 'n/a')} s",
         f"- **Git:** branch `{run.get('git_branch')}`, commit `{(run.get('git_head') or 'n/a')[:10]}`",
         f"- **Workbook SHA-256 (first 16):** `{run.get('workbook_sha256_16')}`",
         f"- **Final grade:** {grade}" + (f" (numbers matched {fg.get('numbers')})" if fg else ""),
         f"- **Reviewer verdict (first → final):** {run.get('reviewer_first_verdict') or 'not run'} → {run.get('reviewer_final_verdict') or 'not run'}",
         f"- **Retry used:** {'n/a' if run.get('retry_used') is None else 'yes' if run['retry_used'] else 'no'}"]
    if run.get("errors"):
        L += ["", "## Errors", *[f"- {e}" for e in run["errors"]]]
    L += ["", "## Evals for this run (05_evals)"]
    for key, label in (("golden", "Golden evals"), ("commentary_grade", "Commentary grade"), ("flawed_control", "Flawed control (must FAIL)"),
                       ("workbook_hash", "Workbook hash before = after")):
        e = ev.get(key) or {}
        L.append(f"- {label}: **{e.get('status', 'n/a')}** {e.get('detail', '')}".rstrip())
    if "regress_fast" in ev:
        L.append(f"- regress --fast: **{ev['regress_fast']['status']}**")
    L += ["", "## Headline numbers (copied from the packet)"]
    if hl:
        L += [f"- Revenue: {_num(hl['revenue'])} (MoM {_num(hl['revenue_mom_pct'], '{:+.1%}')})",
              f"- Gross margin: {_num(hl['gross_margin'], '{:.1%}')}",
              f"- Operating expenses: {_num(hl['operating_expenses'])}",
              f"- Net income: {_num(hl['net_income'])}",
              f"- Cash: {_num(hl['cash'])}" + (f" · runway {_num(hl['runway_months'], '{:.1f}')} months ({hl['runway_window']} burn)" if hl.get("runway_months") is not None else "")]
    else:
        L.append("- Not produced in this run: 02_numbers/review_packet_" + m + ".json")
    L += ["", "## Commentary (final)"]
    if run["mode"] != "claude":
        L.append(NOT_RUN.strip())
    elif final_text:
        L += [final_text.strip()]
    else:
        L.append(f"Not produced in this run: 03_commentary/commentary_{m}_final.md")
    L += ["", "## Open questions"]
    qs = review.get("open_questions") or []
    L += [f"{i}. {q.get('question', '')}" + (f" — {q['why']}" if q.get("why") else "") for i, q in enumerate(qs, 1)] if qs else \
        [NOT_RUN.strip() if run["mode"] != "claude" else "None recorded."]
    (folder / "SUMMARY.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def finalize(folder: Path, with_regress: bool = False, failed: str | None = None) -> dict:
    """Move the work files into the layout, run this run's evals, write SUMMARY.md and run.json. Never deletes the folder."""
    run = read_json(folder / "run.json")
    if not run:
        raise ValueError(f"{folder}/run.json is missing or unreadable")
    run.setdefault("errors", [])
    if failed:
        run["errors"].append(failed)
    timed(run, "Organize", lambda: organize(folder, run))
    if run["mode"] == "claude" and not (folder / "03_commentary" / f"commentary_{run['month']}_final.md").is_file():
        run["errors"].append("Claude stages did not produce a commentary")
    _fill_from_files(folder, run)
    run["evals"] = timed(run, "Evals", lambda: run_evals(folder, run)) or {}
    if with_regress:
        rg = timed(run, "Regress (fast)", lambda: run_regress(folder))
        if rg:
            run["evals"]["regress_fast"] = {"status": "PASS" if rg["held"] else "FAIL", "detail": "scripts/regress.py --fast", "file": "regress_fast.json"}
            (folder / "05_evals" / "evals_summary.json").write_text(json.dumps(run["evals"], indent=2), encoding="utf-8")
    ok = run.get("pipeline_status") == "success" and not run["errors"]
    run["status"] = "complete" if ok else "failed"
    end = datetime.now(timezone.utc)
    run["finished"] = stamps(end)
    run["duration_s"] = round((end - datetime.fromisoformat(run["started"]["utc"])).total_seconds(), 1)
    write_summary(folder, run)
    write_run(folder, run)
    return run


def summary_lines(folder: Path, run: dict) -> list[str]:
    ev, fg = run.get("evals") or {}, run.get("final_grade")
    s = lambda k: (ev.get(k) or {}).get("status", "n/a")  # noqa: E731
    return [f"Run folder: {folder}",
            f"1. run{run['run_number']} · {run['client']} {run['month']} · {run['kind']} · status {run['status'].upper()}",
            f"2. pipeline {run.get('pipeline_status')}" + (f" · errors: {'; '.join(run['errors'])[:200]}" if run.get("errors") else ""),
            "3. commentary: " + ("not run (pipeline only)" if run["mode"] != "claude" else
                                 f"final grade {'PASS' if fg and fg['passed'] else 'FAIL' if fg else 'n/a'}, retry used {run.get('retry_used')}"),
            f"4. reviewer {run.get('reviewer_first_verdict') or 'not run'} → {run.get('reviewer_final_verdict') or 'not run'}, open questions {run.get('open_question_count')}",
            f"5. evals: golden {s('golden')} · commentary {s('commentary_grade')} · flawed control {s('flawed_control')} · hash {s('workbook_hash')}",
            f"6. pack: {run.get('pack_path') or 'not produced'}"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("args", nargs="+", help="<client> <YYYY-MM>   or   finish <run folder>   or   mark <run folder> <stage> start|end|skipped")
    ap.add_argument("--status", help="with mark ... end: the status to record (default done)")
    ap.add_argument("--root", type=Path, default=RUNS, help="where run folders live (tests use a temp folder)")
    ap.add_argument("--claude", action="store_true", help="start a full run: leave the folder open for the Claude stages (/demo-run calls this)")
    ap.add_argument("--with-regress", action="store_true", help="also save python scripts/regress.py --fast into 05_evals/regress_fast.json (about 9 min)")
    ap.add_argument("--failed", help="with finish: record this reason and keep the folder with status failed")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if a.args[0] == "mark":
        if len(a.args) != 4:
            ap.error("mark takes: <run folder> <stage> start|end|skipped")
        try:
            print(json.dumps(mark(Path(a.args[1]), a.args[2], a.args[3], a.status)))
        except ValueError as exc:
            print(f"ERROR: {exc}")
            return 2
        return 0
    if a.args[0] == "finish":
        if len(a.args) != 2:
            ap.error("finish takes one argument: the run folder")
        try:
            run = finalize(Path(a.args[1]), a.with_regress, a.failed)
        except ValueError as exc:
            print(f"ERROR: {exc}")
            return 2
        print("\n".join(summary_lines(Path(a.args[1]), run)))
        return 0 if run["status"] == "complete" else 1
    if len(a.args) != 2:
        ap.error("expected <client> <YYYY-MM>")
    try:
        n, folder = create(a.args[0], a.args[1], a.root, claude=a.claude, with_regress=a.with_regress)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2
    run = read_json(folder / "run.json") or {}
    if a.claude:
        print(f"Run folder: {folder}\nPipeline {run.get('pipeline_status')}; now run the Claude stages, then: python scripts/new_run.py finish {folder}")
        return 0 if run.get("pipeline_status") == "success" else 1
    print("\n".join(summary_lines(folder, run)))
    return 0 if run.get("status") == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())
