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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

OUTPUTS = Path(__file__).resolve().parent.parent / "outputs"
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


DOCS = OUTPUTS.parent / "ai_solutions_builder_free" / "docs"


def load_doc(name: str) -> Loaded:
    """Markdown doc under ai_solutions_builder_free/docs/ (names are fixed by callers, never user input)."""
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
