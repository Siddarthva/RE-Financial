"""The ONLY loader for the Close Review Workspace.

Client data comes from ONE place: a run folder, runs/runN/ (its run.json and its numbered section folders).
A `Run` can open only files inside its own folder; anything else is refused. Nothing here reads outputs/<client>/,
sample outputs or any other run, and nothing here does arithmetic. A file that is not in the run comes back as a
`Loaded` with error "File not found", which pages show as "Not produced in this run: <file name>".

Project pages (Evaluations, Architecture & Security) are not run data. Their files are declared in project_files()
and read only by the load_eval_summary / load_commentary_grade / load_doc functions.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from paths import CLIENTS, DOCS, OUTPUTS, PROJECT, RUNS  # noqa: E402

NOT_FOUND = "File not found"


@dataclass
class Loaded:
    data: Any = None
    path: str = ""          # shown as the source: relative to runs/ for run files
    error: str = ""
    name: str = ""          # file name only

    @property
    def ok(self) -> bool:
        return self.data is not None and not self.error

    @property
    def missing(self) -> bool:
        return self.error == NOT_FOUND


def _rel_run(p: Path) -> str:
    try:
        return p.relative_to(RUNS).as_posix()
    except ValueError:
        return p.as_posix()


def _rel_project(p: Path) -> str:
    try:
        return p.relative_to(PROJECT).as_posix()
    except ValueError:
        return p.as_posix()


def _load(p: Path, rel, parse) -> Loaded:
    if not p.is_file():
        return Loaded(path=rel(p), error=NOT_FOUND, name=p.name)
    try:
        return Loaded(data=parse(p.read_bytes()), path=rel(p), name=p.name)
    except (OSError, ValueError) as exc:
        return Loaded(path=rel(p), error=f"Could not read file: {exc}", name=p.name)


def _json(b: bytes):
    return json.loads(b.decode("utf-8"))


def _jsonl(b: bytes):
    return [json.loads(line) for line in b.decode("utf-8").splitlines() if line.strip()]


def _text(b: bytes):
    return b.decode("utf-8")


# ---- run folders: runs/runN/{SUMMARY.md, run.json, 01_intake .. 06_pack, logs}, written by scripts/new_run.py and /demo-run ----
_RUN_DIR = re.compile(r"^run(\d+)$")
FULL, PIPE = "Full (Claude)", "Pipeline only"
IST = timezone(timedelta(hours=5, minutes=30))
CLAUDE_STAGES = ["Skill draft", "Grade (attempts)", "Review (first)", "Revise", "Review (final)", "Final grade", "Package"]
# key -> path inside the run folder. Nothing outside the folder can be named.
_NAMES = {
    "summary": "SUMMARY.md",
    "intake": "01_intake/intake_{m}.json",
    "packet": "02_numbers/review_packet_{m}.json", "flux": "02_numbers/flux_{m}.json", "tables": "02_numbers/tables_{m}.json",
    "qbo_status": "02_numbers/qbo_status.json", "audit_log": "02_numbers/audit_log.jsonl", "analysis": "02_numbers/analysis.xlsx",
    "commentary_draft": "03_commentary/commentary_{m}_draft.md", "commentary": "03_commentary/commentary_{m}_final.md",
    "grade_record": "03_commentary/commentary_grade_{m}.json", "final_grade": "03_commentary/commentary_final_grade_{m}.json",
    "review_first": "04_review/review_{m}_first.json", "review": "04_review/review_{m}_final.json",
    "golden": "05_evals/golden_results.txt", "grade_report": "05_evals/commentary_grade_report.txt",
    "flawed": "05_evals/flawed_control_check.txt", "hash": "05_evals/workbook_hash.txt", "evals_summary": "05_evals/evals_summary.json",
    "regress": "05_evals/regress_fast.json",
    "pack": "06_pack/monthly_review_{m}.xlsx", "memo": "06_pack/owner_memo_{m}.md", "approval": "06_pack/approval_{m}.json",
    "pipeline_log": "logs/pipeline.log", "claude_log": "logs/claude_session.log",
}


class Run:
    """One run folder. Every read goes through `_path`, which refuses anything outside the folder."""

    def __init__(self, folder: Path):
        self.dir = Path(folder)
        self.name = self.dir.name
        self.number = self.name.removeprefix("run")
        self.run = _load(self.dir / "run.json", _rel_run, _json)
        self.run.name = "run.json"
        self.client = self.month = None
        if self.run.ok and isinstance(self.run.data, dict):
            self.client, self.month = self.run.data.get("client"), self.run.data.get("month")
        if not self.month and self.dir.is_dir():  # run.json absent: take the month from the folder so the page still opens
            hit = next(iter(sorted((self.dir / "02_numbers").glob("review_packet_*.json"))), None)
            if hit:
                self.month = hit.stem.removeprefix("review_packet_")
                loaded = _load(hit, _rel_run, _json)
                self.client = loaded.data.get("client") if loaded.ok and isinstance(loaded.data, dict) else None

    @property
    def r(self) -> dict:
        return self.run.data if self.run.ok and isinstance(self.run.data, dict) else {}

    @property
    def folder(self) -> str:
        return _rel_project(self.dir)

    def filename(self, key: str) -> str:
        """Path of the file inside the run folder, e.g. 02_numbers/review_packet_2026-06.json."""
        return _NAMES[key].format(m=self.month)

    def _path(self, rel: str) -> Path:
        p = (self.dir / rel).resolve()
        try:
            p.relative_to(self.dir.resolve())
        except ValueError:
            raise ValueError(f"{rel!r} is outside the run folder") from None
        return self.dir / rel

    def _load(self, rel: str, parse) -> Loaded:
        got = _load(self._path(rel), _rel_run, parse)
        got.name = rel  # pages say "Not produced in this run: <path inside the run folder>"
        return got

    def json(self, key: str) -> Loaded:
        name = self.filename(key)
        return self._load(name, _jsonl if name.endswith(".jsonl") else _json)

    def text(self, key: str) -> Loaded:
        return self._load(self.filename(key), _text)

    def pack(self) -> tuple[str, bytes] | None:
        p = self._path(self.filename("pack"))
        return (p.name, p.read_bytes()) if p.is_file() else None

    def manifest(self) -> Loaded:
        """The pipeline manifest the run folder holds (newest by name; names sort by UTC timestamp)."""
        d = self.dir / "02_numbers"
        found = sorted(d.glob("manifest_*.json")) if d.is_dir() else []
        if not found:
            return Loaded(path=_rel_run(d / "manifest_<run>.json"), error=NOT_FOUND, name="02_numbers/manifest_<run>.json")
        return self._load(f"02_numbers/{found[-1].name}", _json)

    def files(self, section: str) -> list[Path]:
        """Files directly inside one section folder of this run."""
        d = self._path(section)
        return sorted(p for p in d.iterdir() if p.is_file()) if d.is_dir() else []

    def all_json(self) -> list[Loaded]:
        """Every JSON file in the run (run.json and the numbered sections), for the raw expanders."""
        out = [self.run] if self.run.ok else []
        for s in ("01_intake", "02_numbers", "03_commentary", "04_review", "05_evals", "06_pack"):
            out += [self._load(f"{s}/{p.name}", _json) for p in self.files(s) if p.suffix == ".json"]
        return out

    def excel_files(self) -> list[Path]:
        return [p for s in ("06_pack", "02_numbers") for p in self.files(s) if p.suffix == ".xlsx"]

    def missing_files(self) -> list[str]:
        out = [] if self.run.ok else ["run.json"]
        for key in ("packet", "review", "review_first", "grade_record", "final_grade", "flux", "commentary", "memo"):
            got = self.text(key) if key in ("commentary", "memo") else self.json(key)
            if not got.ok:
                out.append(self.filename(key))
        if self.pack() is None:
            out.append(self.filename("pack"))
        return out

    def not_run(self, section: str) -> str | None:
        """The text of <section>/NOT_RUN.md when this run did not execute that stage, else None."""
        p = self._path(f"{section}/NOT_RUN.md")
        return p.read_text(encoding="utf-8") if p.is_file() else None

    def bundle(self) -> dict:
        """Every file the run page shows, as Loaded objects (pack: (name, bytes) or None), plus the file names and what is missing."""
        keys = ("packet", "review", "review_first", "grade_record", "final_grade", "flux", "evals_summary", "regress")
        res = {"run_obj": self, "dir": self.dir, "client": self.client, "month": self.month, "run": self.run,
               "files": {k: self.filename(k) for k in _NAMES}, "missing": self.missing_files()}
        res.update({k: self.json(k) for k in keys})
        res.update({k: self.text(k) for k in ("summary", "commentary", "commentary_draft", "memo", "golden", "grade_report", "flawed", "hash")})
        res["pack"] = self.pack()
        return res

    def final_grade(self) -> dict | None:
        """run.json first, then the grade file: {'passed','numbers','mismatches'} or None."""
        fg = self.r.get("final_grade")
        if not fg:
            f = self.json("final_grade")
            fg = f.data if f.ok else None
        return fg or None

    def kind(self) -> str:
        return self.r.get("kind") or (FULL if self.r.get("mode") == "claude" else PIPE)

    def failed(self) -> bool:
        return self.r.get("status") == "failed"

    def grade_text(self, from_files: bool = True) -> str:
        """PASS / FAIL / not graded. from_files=False reads run.json only (the run list must not open other runs' files)."""
        fg = self.final_grade() if from_files else self.r.get("final_grade")
        return "not graded" if not fg else "PASS" if fg.get("passed") else "FAIL"

    def clock(self) -> str:
        return ((self.r.get("started") or {}).get("ist") or "")[11:16]

    def label(self) -> str:
        """'Run 3 · abc 2026-06 · 12:10 IST · Full (Claude) · PASS' (text only, from run.json)."""
        parts = [f"Run {self.number}"]
        if self.client and self.month:
            parts.append(f"{self.client} {self.month}")
        if self.clock():
            parts.append(f"{self.clock()} IST")
        end = "FAILED" if self.failed() else self.grade_text(from_files=False).upper() if self.kind() == FULL else "no grade"
        return " · ".join(parts + [self.kind(), end])


def list_runs() -> list[Run]:
    """Run folders, newest (highest number) first, sorted as numbers (run10 after run9). Empty when runs/ does not exist."""
    if not RUNS.is_dir():
        return []
    found = [(int(m.group(1)), p) for p in RUNS.iterdir() if p.is_dir() and (m := _RUN_DIR.match(p.name))]
    return [Run(p) for _, p in sorted(found, reverse=True)]


def list_clients() -> list[str]:
    """Client ids a new run can be started for (folders under clients/ with a config.yaml). Names only; no file is opened."""
    if not CLIENTS.is_dir():
        return []
    return sorted(d.name for d in CLIENTS.iterdir() if d.is_dir() and (d / "config.yaml").is_file())


# ---- run table and stage timelines: read from run.json only ----
def _utc(iso) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(iso))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _ist(iso) -> str:
    t = _utc(iso)
    return t.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S") if t else "n/a"


def run_row(run: Run) -> dict:
    r = run.r
    started = (r.get("started") or {}).get("utc") or ""
    status = r.get("status") or r.get("pipeline_status") or "n/a"
    full = run.kind() == FULL
    if full and r.get("final_grade") is None and status != "failed":
        status += " (Claude stages incomplete)"
    return {"run": f"Run {run.number}", "kind": run.kind(), "started": _ist(started) if started else "n/a",
            "client": run.client, "period": run.month, "final_grade": run.grade_text(from_files=False) if full else "not run",
            "verdict": (r.get("reviewer_final_verdict") or "not recorded") if full else "not run",
            "sha": (r.get("git_head") or "n/a")[:7], "status": status}


def run_timeline(run: Run) -> list[dict]:
    """Stage rows {Stage, Status, Started (IST), duration_s}. Claude stages of a pipeline-only run say 'not run'."""
    c, out = run.r, []
    t, stages = c.get("timings") or {}, c.get("stages") or {}
    unset = "not run" if run.kind() == PIPE else "not recorded"

    def add(name, status, started=None, dur=None):
        out.append({"Stage": name, "Status": status, "Started (IST)": _ist(started) if started else "n/a", "duration_s": dur})

    fallback = {"Intake": "Intake", "Calculate": "Calculate", "Skill draft": "Commentary draft",
                "Review (final)": "Review", "Package": "Package"}
    names = ["Intake", "Calculate", "Skill draft"]
    attempts = sorted((n for n in t if n.startswith("Grade attempt")), key=lambda n: int(n.rsplit(" ", 1)[1]))
    names += attempts or ["Grade (attempts)"]
    names += ["Review (first)", "Revise", "Review (final)", "Final grade", "Package"]
    names += [n for n in ("Organize", "Evals", "Regress (fast)") if n in t]
    for name in names:
        e = t.get(name)
        if e:
            add(name, e.get("status") or "done", e.get("started"), e.get("duration_s"))
        elif name == "Final grade" and c.get("final_grade"):
            add(name, "PASS" if c["final_grade"].get("passed") else "FAIL")
        elif name == "Grade (attempts)" and c.get("grade_attempts"):
            add(name, f"{len(c['grade_attempts'])} attempt(s) recorded")
        else:
            add(name, stages.get(fallback.get(name, "")) or unset)
    return out


# ---- project pages: NOT run data. Their files are declared here and nowhere else ----
def project_files(page: str) -> list[Path]:
    return {"evaluations": [OUTPUTS / "eval_results.json", OUTPUTS / "commentary_grade.json"],
            "architecture": [DOCS / "architecture.md", DOCS / "workflow.md", DOCS / "brief_traceability.md"]}[page]


def file_date(p: Path) -> str:
    """Last-modified date of a project file (UTC), or 'file not found'."""
    try:
        return datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d")
    except OSError:
        return "file not found"


def project_sources(page: str) -> list[tuple[str, str]]:
    return [(_rel_project(p), file_date(p)) for p in project_files(page)]


def load_eval_summary() -> Loaded:
    """outputs/eval_results.json, written by scripts/export_eval_results.py from the existing eval scripts."""
    return _load(project_files("evaluations")[0], _rel_project, _json)


def load_commentary_grade() -> Loaded:
    return _load(project_files("evaluations")[1], _rel_project, _json)


def load_doc(name: str) -> Loaded:
    """Markdown doc under 04_architecture/ (names are fixed by callers, never user input)."""
    return _load(DOCS / name, _rel_project, _text)
