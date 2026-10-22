"""Create the next numbered demo run folder and run the deterministic stages into it.

    python scripts/new_run.py abc 2026-06                   # creates demo_runs/output_NNN/ and runs intake + calculate there
    python scripts/new_run.py mark demo_runs/output_001 "Skill draft" start   # also: end [--status X], skipped
    python scripts/new_run.py finish demo_runs/output_001   # records the outcome of the later stages in run.json

`new_run` never writes to outputs/. The folder number is the next free one and is never reused or overwritten.
Inside the folder the layout is the normal one: demo_runs/output_NNN/<client>/... plus demo_runs/output_NNN/run.json.
The /demo-run command does the draft / grade / review / pack steps into the same folder and then calls `finish`,
which fills run.json from the files those steps left behind. Nothing here approves anything.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

import run_client  # noqa: E402

DEMO_RUNS = PROJECT / "demo_runs"
IST = timezone(timedelta(hours=5, minutes=30))
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
FOLDER = re.compile(r"^output_(\d{3,})$")
STAGE = re.compile(r"^(Skill draft|Review \((first|final)\)|Revise|Final grade|Package|Grade attempt [1-9]\d*)$")


def stamps(t: datetime) -> dict:
    return {"utc": t.astimezone(timezone.utc).isoformat(timespec="seconds"), "ist": t.astimezone(IST).isoformat(timespec="seconds")}


def _git(*args: str) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=PROJECT, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
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
    """Create root/output_NNN with the next free number. mkdir without exist_ok makes overwriting impossible."""
    root.mkdir(parents=True, exist_ok=True)
    while True:
        nums = [int(m.group(1)) for p in root.iterdir() if (m := FOLDER.match(p.name))]
        n = max(nums, default=0) + 1
        folder = root / f"output_{n:03d}"
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


def write_run(folder: Path, run: dict) -> None:
    (folder / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")


def create(client: str, month: str, root: Path = DEMO_RUNS, clients_root: Path = run_client.CLIENTS_ROOT) -> tuple[int, Path]:
    err = validate(client, month, clients_root)
    if err:
        raise ValueError(err)
    started = datetime.now(timezone.utc)
    n, folder = next_folder(root)
    r = subprocess.run([sys.executable, str(PROJECT / "scripts" / "run_pipeline.py"), client, month,
                        "--clients-root", str(clients_root), "--outputs-root", str(folder)],
                       cwd=PROJECT, capture_output=True, text=True, encoding="utf-8")
    out = folder / client
    manifests = sorted(out.glob(f"manifest_*-{client}-{month}.json"))
    manifest = read_json(manifests[-1]) if manifests else None
    stages = {s["name"]: s["status"] for s in (manifest or {}).get("stages", [])}
    if "Grade commentary" in stages and not (out / f"commentary_{month}.md").is_file():
        stages["Grade commentary"] = "skipped (no draft yet)"
    for later in ("Commentary draft", "Review", "Package"):  # the Claude stages: a pipeline-only run says so; `finish` overwrites these
        stages.setdefault(later, "not run")
    intake = read_json(out / f"intake_{month}.json") or {}
    timings, t = {}, started
    for st_ in (manifest or {}).get("stages", []):  # Intake and Calculate run back to back, so start = previous end
        if st_.get("name") in ("Intake", "Calculate") and isinstance(st_.get("duration_s"), (int, float)):
            end = t + timedelta(seconds=st_["duration_s"])
            timings[st_["name"]] = {"started": stamps(t)["utc"], "ended": stamps(end)["utc"],
                                    "duration_s": round(st_["duration_s"], 1), "status": st_.get("status")}
            t = end
    write_run(folder, {
        "run_number": n, "run_id": folder.name, "client": client, "month": month,
        "started": stamps(started), "finished": stamps(datetime.now(timezone.utc)),
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"), "git_head": _git("rev-parse", "HEAD"),
        "workbook_sha256_16": (intake.get("sha256") or "")[:16] or None,
        "pipeline_status": (manifest or {}).get("status", "failed" if r.returncode else "unknown"),
        "stages": stages, "timings": timings,
        "grade_attempts": None, "retry_used": None, "reviewer_first_verdict": None, "reviewer_final_verdict": None,
        "final_grade": None, "pack_path": None, "open_question_count": None,
    })
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


def finish(folder: Path) -> dict:
    """Fill run.json from the files the draft / grade / review / pack steps left in this folder."""
    run = read_json(folder / "run.json")
    if not run:
        raise ValueError(f"{folder}/run.json is missing or unreadable")
    client, month = run["client"], run["month"]
    out = folder / client
    rec = read_json(out / f"commentary_grade_{month}.json") or {}
    first = read_json(out / f"review_{month}_first.json") or {}
    final = read_json(out / f"review_{month}.json") or {}
    fg = read_json(out / f"commentary_final_grade_{month}.json")
    pack = out / f"monthly_review_{month}.xlsx"
    run["grade_attempts"] = [{"attempt": i, "passed": a.get("passed"), "numbers": a.get("numbers"), "mismatches": a.get("mismatches", [])}
                             for i, a in enumerate(rec.get("attempts", []), 1)] or None
    run["retry_used"] = rec.get("retry_used")
    run["reviewer_first_verdict"] = first.get("verdict")
    run["reviewer_final_verdict"] = final.get("verdict")
    run["final_grade"] = {"passed": fg["passed"], "numbers": fg["numbers"], "mismatches": fg["mismatches"]} if fg else None
    run["pack_path"] = pack.relative_to(folder).as_posix() if pack.is_file() else None  # relative to the run folder
    run["open_question_count"] = len(final["open_questions"]) if isinstance(final.get("open_questions"), list) else None
    stages = run.setdefault("stages", {})
    stages["Commentary draft"] = "done" if (out / f"commentary_{month}.md").is_file() else "not run"
    stages["Review"] = "done" if final else "not run"
    stages["Package"] = "done" if pack.is_file() and (out / f"owner_memo_{month}.md").is_file() else "not run"
    # Stage outcomes in the timeline come from the same files; a revision that was never needed is recorded as skipped.
    tm = run.setdefault("timings", {})
    for i, a in enumerate(rec.get("attempts", []), 1):
        if f"Grade attempt {i}" in tm:
            tm[f"Grade attempt {i}"]["status"] = "PASS" if a.get("passed") else "FAIL"
    if "Final grade" in tm and fg:
        tm["Final grade"]["status"] = "PASS" if fg["passed"] else "FAIL"
    for key, v in (("Review (first)", first.get("verdict")), ("Review (final)", final.get("verdict"))):
        if key in tm and v:
            tm[key]["status"] = v
    if "Revise" not in tm and first.get("verdict") == "approve":
        tm["Revise"] = {"started": None, "ended": None, "duration_s": 0.0, "status": "skipped (first review approved)"}
    if "Review (final)" not in tm and first.get("verdict") == "approve":
        tm["Review (final)"] = {"started": None, "ended": None, "duration_s": 0.0, "status": "skipped (first review is final)"}
    run["finished"] = stamps(datetime.now(timezone.utc))
    write_run(folder, run)
    return run


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("args", nargs="+", help="<client> <YYYY-MM>   or   finish <run folder>   or   mark <run folder> <stage> start|end|skipped")
    ap.add_argument("--status", help="with mark ... end: the status to record (default done)")
    ap.add_argument("--root", type=Path, default=DEMO_RUNS, help="where run folders live (tests use a temp folder)")
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
            run = finish(Path(a.args[1]))
        except ValueError as exc:
            print(f"ERROR: {exc}")
            return 2
        print(json.dumps({k: run[k] for k in ("run_id", "grade_attempts", "reviewer_first_verdict", "reviewer_final_verdict",
                                              "final_grade", "pack_path", "open_question_count")}, indent=2))
        return 0
    if len(a.args) != 2:
        ap.error("expected <client> <YYYY-MM>")
    try:
        n, folder = create(a.args[0], a.args[1], a.root)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(folder)
    return 0 if (read_json(folder / "run.json") or {}).get("pipeline_status") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
