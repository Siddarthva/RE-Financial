"""The ONLY loader for the Close Review Workspace.

Reads JSON files under <project>/outputs/<client>/ and returns them as-is.
It performs no financial calculations. Every function returns a `Loaded`
so pages can show an explicit empty state when a file is missing or invalid.

Expected layout (files the engine may or may not have produced yet):
  outputs/<client>/summary.json
  outputs/<client>/review_packet_<YYYY-MM>.json
  outputs/<client>/review_<YYYY-MM>.json
  outputs/<client>/qbo_load_plan.json
  outputs/<client>/manifest*.json          (run manifests)
  outputs/<client>/audit_log.json | audit_log.jsonl
  outputs/commentary_grade.json            (eval result, global)
  outputs/<client>/eval_results*.json      (eval results, per client)
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from paths import DEMO_RUNS, DOCS, OUTPUTS  # noqa: E402
_PERIOD_RE = re.compile(r"review_packet_(\d{4}-\d{2})\.json$")


@dataclass
class Loaded:
    data: Any = None
    path: str = ""
    error: str = ""
    sources: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.data is not None and not self.error


def _rel(p: Path) -> str:
    try:
        return p.relative_to(OUTPUTS.parent).as_posix()
    except ValueError:
        return p.as_posix()


def _read_json(p: Path) -> Loaded:
    if not p.is_file():
        return Loaded(path=_rel(p), error="File not found")
    try:
        return Loaded(data=json.loads(p.read_text(encoding="utf-8")), path=_rel(p))
    except (OSError, ValueError) as exc:
        return Loaded(path=_rel(p), error=f"Could not read file: {exc}")


def _read_many(paths: list[Path], label: str) -> Loaded:
    if not paths:
        return Loaded(path=label, error="No matching files")
    items, errors = [], []
    for p in paths:
        r = _read_json(p)
        if r.ok:
            items.append({"file": r.path, "content": r.data})
        else:
            errors.append(f"{r.path}: {r.error}")
    return Loaded(data=items or None, path=label, error="; ".join(errors) if not items else "",
                  sources=[i["file"] for i in items])


def list_clients() -> list[str]:
    if not OUTPUTS.is_dir():
        return []
    return sorted(d.name for d in OUTPUTS.iterdir() if d.is_dir() and (d / "summary.json").is_file())


def list_periods(client: str) -> list[str]:
    d = OUTPUTS / client
    if not d.is_dir():
        return []
    found = (m.group(1) for f in d.iterdir() if (m := _PERIOD_RE.search(f.name)))
    return sorted(found, reverse=True)


def load_summary(client: str) -> Loaded:
    return _read_json(OUTPUTS / client / "summary.json")


def load_packet(client: str, period: str | None) -> Loaded:
    if not period:
        return Loaded(path=f"outputs/{client}/review_packet_<period>.json", error="No period available")
    return _read_json(OUTPUTS / client / f"review_packet_{period}.json")


def load_review(client: str, period: str | None) -> Loaded:
    if not period:
        return Loaded(path=f"outputs/{client}/review_<period>.json", error="No period available")
    return _read_json(OUTPUTS / client / f"review_{period}.json")


def load_load_plan(client: str) -> Loaded:
    return _read_json(OUTPUTS / client / "qbo_load_plan.json")


def load_manifests(client: str) -> Loaded:
    d = OUTPUTS / client
    paths = sorted(d.glob("manifest*.json")) if d.is_dir() else []
    return _read_many(paths, f"outputs/{client}/manifest*.json")


def load_audit_log(client: str) -> Loaded:
    d = OUTPUTS / client
    label = f"outputs/{client}/audit_log.json[l]"
    jl, js = d / "audit_log.jsonl", d / "audit_log.json"
    if jl.is_file():
        try:
            rows = [json.loads(line) for line in jl.read_text(encoding="utf-8").splitlines() if line.strip()]
            return Loaded(data=rows, path=_rel(jl))
        except (OSError, ValueError) as exc:
            return Loaded(path=_rel(jl), error=f"Could not read file: {exc}")
    if js.is_file():
        r = _read_json(js)
        if r.ok and isinstance(r.data, dict):
            r.data = r.data.get("events", [r.data])
        return r
    return Loaded(path=label, error="File not found")


def load_eval_results(client: str) -> Loaded:
    paths = [OUTPUTS / "commentary_grade.json"]
    d = OUTPUTS / client
    if d.is_dir():
        paths += sorted(d.glob("eval_results*.json"))
    return _read_many([p for p in paths if p.is_file()], "outputs/commentary_grade.json, outputs/<client>/eval_results*.json")


# ---- period-scoped engine outputs (all written by scripts/run_pipeline.py and friends) ----
def _period_file(client: str, kind: str, period: str | None) -> Loaded:
    if not period:
        return Loaded(path=f"outputs/{client}/{kind}_<period>.json", error="No period available")
    return _read_json(OUTPUTS / client / f"{kind}_{period}.json")


def load_intake(client: str, period: str | None) -> Loaded:
    return _period_file(client, "intake", period)


def load_flux(client: str, period: str | None) -> Loaded:
    return _period_file(client, "flux", period)


def load_tables(client: str, period: str | None) -> Loaded:
    return _period_file(client, "tables", period)


def load_commentary(client: str, period: str | None) -> Loaded:
    return _period_file(client, "commentary", period)


def load_approval(client: str, period: str | None) -> Loaded:
    return _period_file(client, "approval", period)


def load_qbo_status(client: str) -> Loaded:
    return _read_json(OUTPUTS / client / "qbo_status.json")


def latest_manifest(client: str, period: str | None) -> Loaded:
    """Most recent run manifest for the period (manifest filenames sort by UTC timestamp)."""
    d = OUTPUTS / client
    paths = sorted(d.glob(f"manifest_*-{client}-{period}.json")) if d.is_dir() and period else []
    return _read_json(paths[-1]) if paths else Loaded(path=f"outputs/{client}/manifest_<run>-{client}-{period}.json",
                                                      error="No run manifest for this period")


def downstream_status(client: str, period: str | None) -> dict[str, dict]:
    """Status of the stages that leave files behind (Skill draft, Review, Package, Approved)."""
    d = OUTPUTS / client

    def f(name: str) -> Path:
        return d / name

    def stat(p: Path) -> dict:
        return {"status": "done" if p.is_file() else "pending", "file": _rel(p)}

    if not period:
        return {}
    review = f(f"review_{period}.json")
    out = {
        "Skill draft": stat(f(f"commentary_{period}.md")),
        "Review": stat(review),
        "Package": stat(f(f"monthly_review_{period}.xlsx")),
    }
    ap = load_approval(client, period)
    out["Approved"] = {"status": ap.data.get("status", "pending") if ap.ok else "pending", "file": ap.path}
    return out


def load_eval_summary() -> Loaded:
    """outputs/eval_results.json, written by scripts/export_eval_results.py from the existing eval scripts."""
    return _read_json(OUTPUTS / "eval_results.json")


def load_commentary_grade() -> Loaded:
    return _read_json(OUTPUTS / "commentary_grade.json")


def load_doc(name: str) -> Loaded:
    """Markdown doc under 04_architecture/ (names are fixed by callers, never user input)."""
    p = DOCS / name
    if not p.is_file():
        return Loaded(path=_rel(p), error="File not found")
    try:
        return Loaded(data=p.read_text(encoding="utf-8"), path=_rel(p))
    except OSError as exc:
        return Loaded(path=_rel(p), error=f"Could not read file: {exc}")


def reviewer_excel(client: str, period: str | None) -> tuple[str, bytes] | None:
    if not period:
        return None
    p = OUTPUTS / client / f"monthly_review_{period}.xlsx"
    return (p.name, p.read_bytes()) if p.is_file() else None


# ---- demo runs: demo_runs/output_NNN/{run.json, <client>/...}, written by scripts/new_run.py and the /demo-run command ----
_RUN_DIR = re.compile(r"^output_(\d{3,})$")


def list_demo_runs() -> list[Path]:
    """Run folders, newest (highest number) first. Empty when demo_runs/ does not exist."""
    if not DEMO_RUNS.is_dir():
        return []
    found = [(int(m.group(1)), p) for p in DEMO_RUNS.iterdir() if p.is_dir() and (m := _RUN_DIR.match(p.name))]
    return [p for _, p in sorted(found, reverse=True)]


def _read_text(p: Path) -> Loaded:
    if not p.is_file():
        return Loaded(path=_rel(p), error="File not found")
    try:
        return Loaded(data=p.read_text(encoding="utf-8"), path=_rel(p))
    except OSError as exc:
        return Loaded(path=_rel(p), error=f"Could not read file: {exc}")


def load_demo_run(run_dir: Path) -> dict:
    """Every file of one run, as Loaded objects, plus the names of the files that are missing. Client and month come
    from run.json; if that is absent they are taken from the folder contents so the page still opens."""
    run_dir = Path(run_dir)
    run = _read_json(run_dir / "run.json")
    client = month = None
    if run.ok:
        client, month = run.data.get("client"), run.data.get("month")
    if not (client and month):
        for sub in sorted(p for p in run_dir.iterdir() if p.is_dir()) if run_dir.is_dir() else []:
            hit = next(iter(sorted(sub.glob("review_packet_*.json"))), None)
            if hit:
                client, month = sub.name, hit.stem.removeprefix("review_packet_")
                break
    out = run_dir / client if client else run_dir
    names = {
        "packet": f"review_packet_{month}.json", "review": f"review_{month}.json", "review_first": f"review_{month}_first.json",
        "grade_record": f"commentary_grade_{month}.json", "final_grade": f"commentary_final_grade_{month}.json",
        "flux": f"flux_{month}.json", "commentary": f"commentary_{month}.md", "memo": f"owner_memo_{month}.md",
        "pack": f"monthly_review_{month}.xlsx",
    }
    res = {"dir": run_dir, "client": client, "month": month, "run": run, "files": {}, "missing": []}
    if not run.ok:
        res["missing"].append("run.json")
    for key, name in names.items():
        p = out / name
        res["files"][key] = name
        if key in ("commentary", "memo"):
            res[key] = _read_text(p)
        elif key == "pack":
            res[key] = (name, p.read_bytes()) if p.is_file() else None
        else:
            res[key] = _read_json(p)
        got = res[key]
        if got is None or (isinstance(got, Loaded) and not got.ok):
            res["missing"].append(f"{client}/{name}" if client else name)
    return res


# ---- one runs list: demo runs ("Full (Claude)") and pipeline manifests ("Pipeline only"), plus stage timelines ----
FULL, PIPE = "Full (Claude)", "Pipeline only"
IST = timezone(timedelta(hours=5, minutes=30))
CLAUDE_STAGES = ["Skill draft", "Grade (attempts)", "Review (first)", "Revise", "Review (final)", "Final grade", "Package"]


def _utc(iso) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(iso))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _ist(iso) -> str:
    t = _utc(iso)
    return t.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S") if t else "n/a"


def _grade_text(fg) -> str:
    if not fg:
        return "not recorded"
    return f"{'PASS' if fg.get('passed') else 'FAIL'} {fg.get('numbers') or ''}".strip()


def list_all_runs(client: str) -> list[dict]:
    """Every run for the client, newest first. Reads run.json and manifests only; nothing is computed."""
    rows = []
    for d in list_demo_runs():
        run = _read_json(d / "run.json")
        r = run.data if run.ok else {}
        who = r.get("client") or next((p.name for p in sorted(d.iterdir()) if p.is_dir()), None)
        if who != client:
            continue
        started = (r.get("started") or {}).get("utc") or ""
        status = r.get("pipeline_status") or "n/a"
        if r.get("final_grade") is None:
            status += " (Claude stages incomplete)"
        rows.append({"key": f"demo:{d.name}", "kind": FULL, "run": f"Output {d.name.removeprefix('output_')}", "sort": started,
                     "started": _ist(started) if started else "n/a", "period": r.get("month"),
                     "final_grade": _grade_text(r.get("final_grade")),
                     "verdict": r.get("reviewer_final_verdict") or "not recorded",
                     "sha": (r.get("git_head") or "n/a")[:7], "status": status, "dir": d, "content": r})
    man = load_manifests(client)
    for item in (man.data if man.ok else []):
        c = item["content"]
        started = c.get("started_at") or ""
        rows.append({"key": f"pipe:{c.get('run_id')}", "kind": PIPE, "run": c.get("run_id"), "sort": started,
                     "started": _ist(started) if started else "n/a", "period": c.get("period"),
                     "final_grade": "not run", "verdict": "not run", "sha": c.get("git_sha") or "n/a",
                     "status": c.get("status"), "dir": None, "content": c})
    key = lambda x: (_utc(x["sort"]) or datetime.min.replace(tzinfo=timezone.utc), x["run"] or "")  # noqa: E731
    return sorted(rows, key=key, reverse=True)


def run_timeline(row: dict) -> list[dict]:
    """Stage rows {Stage, Status, Started (IST), duration_s} for one run. Claude stages of a pipeline-only run say 'not run'."""
    c = row["content"]
    out = []

    def add(name, status, started=None, dur=None):
        out.append({"Stage": name, "Status": status, "Started (IST)": _ist(started) if started else "n/a", "duration_s": dur})

    if row["kind"] == PIPE:
        by = {s.get("name"): s for s in c.get("stages", [])}
        for name in ("Intake", "Calculate"):
            s = by.pop(name, None)
            add(name, s.get("status") if s else "not recorded", None, s.get("duration_s") if s else None)
        for name in CLAUDE_STAGES:
            add(name, "not run")
        for name, s in by.items():
            add(name, s.get("status"), None, s.get("duration_s"))
        return out
    t, stages = c.get("timings") or {}, c.get("stages") or {}
    fallback = {"Intake": "Intake", "Calculate": "Calculate", "Skill draft": "Commentary draft",
                "Review (final)": "Review", "Package": "Package"}
    names = ["Intake", "Calculate", "Skill draft"]
    attempts = sorted((n for n in t if n.startswith("Grade attempt")), key=lambda n: int(n.rsplit(" ", 1)[1]))
    names += attempts or ["Grade (attempts)"]
    names += ["Review (first)", "Revise", "Review (final)", "Final grade", "Package"]
    for name in names:
        e = t.get(name)
        if e:
            add(name, e.get("status") or "done", e.get("started"), e.get("duration_s"))
        elif name == "Final grade" and c.get("final_grade"):
            add(name, "PASS" if c["final_grade"].get("passed") else "FAIL")
        elif name == "Grade (attempts)" and c.get("grade_attempts"):
            add(name, f"{len(c['grade_attempts'])} attempt(s) recorded")
        else:
            add(name, stages.get(fallback.get(name, ""), "not recorded"))
    return out
