"""Break a client config on purpose, one field at a time, and record what the pipeline does.

    python 02_skill/config_break_lab.py            # writes 02_skill/config_break_lab_results.json, prints a table

Each case copies a client's folder to a temp clients root, damages ONE config field, runs
`scripts/run_pipeline.py <client> <month>` against it (temp outputs root), and records the exit code, the stage that
stopped, and the first message. Nothing under clients/ or outputs/ is touched. CONFIG_REFERENCE.md quotes these results,
so its "what breaks" column is observed, not guessed. Used by tests/test_config_break_lab.py.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RESULTS = Path(__file__).with_name("config_break_lab_results.json")
MONTH = {"xyz": "2026-05", "abc": "2026-06"}


def _set(cfg, path, value):
    cur = cfg
    for k in path[:-1]:
        cur = cur[k]
    cur[path[-1]] = value


def _del(cfg, path):
    cur = cfg
    for k in path[:-1]:
        cur = cur[k]
    del cur[path[-1]]


# (id, base client, field, description, mutation)
CASES = [
    ("baseline", "xyz", "(none)", "unchanged config", lambda c: None),
    ("client_mismatch", "xyz", "client", "id differs from folder name", lambda c: _set(c, ["client"], "zzz")),
    ("no_display_name", "xyz", "display_name", "key removed", lambda c: _del(c, ["display_name"])),
    ("workbook_missing", "xyz", "workbook", "path to a file that does not exist", lambda c: _set(c, ["workbook"], "nope.xlsx")),
    ("sheet_wrong", "xyz", "sheets.income_statement", "sheet name not in workbook", lambda c: _set(c, ["sheets", "income_statement"], "Profit and Loss")),
    ("header_label_wrong", "xyz", "layout.header_label", "label not found in the sheet", lambda c: _set(c, ["layout", "header_label"], "Account")),
    ("month_format_wrong", "xyz", "layout.month_format", "format does not match the header cells", lambda c: _set(c, ["layout", "month_format"], "%b %Y")),
    ("section_header_wrong", "xyz", "sections.income.header", "row label not in the sheet", lambda c: _set(c, ["sections", "income", "header"], "Sales")),
    ("section_total_wrong", "xyz", "sections.income.total", "row label not in the sheet", lambda c: _set(c, ["sections", "income", "total"], "Total Sales")),
    ("section_missing", "xyz", "sections", "one section removed", lambda c: _del(c, ["sections", "cost of goods sold"])),
    ("total_label_wrong", "xyz", "totals.revenue", "row label not in the sheet", lambda c: _set(c, ["totals", "revenue"], "Turnover")),
    ("total_key_missing", "xyz", "totals", "gross_profit key removed", lambda c: _del(c, ["totals", "gross_profit"])),
    ("subtotal_not_a_list", "xyz", "subtotal_rows", "wrong type (string, not list)", lambda c: _set(c, ["subtotal_rows"], "Marketing")),
    ("fy_start_13", "xyz", "fiscal_year.start_month", "month 13", lambda c: _set(c, ["fiscal_year", "start_month"], 13)),
    ("fy_start_wrong_but_valid", "xyz", "fiscal_year.start_month", "valid but wrong month (1 instead of 4)", lambda c: _set(c, ["fiscal_year", "start_month"], 1)),
    ("category_undeclared", "xyz", "categories", "a used category removed from the list", lambda c: c["categories"].remove("Technology")),
    ("category_unused", "xyz", "categories", "extra category with no accounts", lambda c: c["categories"].append("Insurance")),
    ("account_unmapped", "xyz", "account_to_category", "one account's mapping deleted", lambda c: _del(c, ["account_to_category", "Utilities"])),
    ("account_typo", "xyz", "account_to_category", "mapping key misspelt", lambda c: (_del(c, ["account_to_category", "Utilities"]), _set(c, ["account_to_category", "Utilitys"], "General & Administrative"))),
    ("materiality_unknown_key", "xyz", "thresholds.materiality", "unknown setting name", lambda c: _set(c, ["thresholds"], {"materiality": {"min_dollar": 1}})),
    ("materiality_negative", "xyz", "thresholds.materiality", "negative threshold", lambda c: _set(c, ["thresholds"], {"materiality": {"min_dollars": -5}})),
    ("margin_drop_text", "xyz", "thresholds.gross_margin_drop_pp", "text instead of number", lambda c: _set(c, ["thresholds"], {"gross_margin_drop_pp": "five"})),
    ("subtotal_omitted", "abc", "subtotal_rows", "all subtotal labels removed (children double-counted)", lambda c: _set(c, ["subtotal_rows"], [])),
    ("bs_sheet_wrong", "abc", "sheets.balance_sheet", "sheet name not in workbook", lambda c: _set(c, ["sheets", "balance_sheet"], "BS")),
    ("bs_rows_wrong", "abc", "balance_sheet_rows", "override label not in the Balance Sheet", lambda c: _set(c, ["balance_sheet_rows"], {"total_assets": "Sum of Assets"})),
]


def run_case(case, month=None) -> dict:
    cid, base, field, desc, mutate = case
    month = month or MONTH[base]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        clients = tmp / "clients"
        dest = clients / base
        shutil.copytree(ROOT / "clients" / base, dest, ignore=shutil.ignore_patterns("__pycache__", "*.py"))
        wb = (ROOT / "clients" / base / (yaml.safe_load((ROOT / "clients" / base / "config.yaml").read_text(encoding="utf-8"))["workbook"])).resolve()
        cfg = yaml.safe_load((dest / "config.yaml").read_text(encoding="utf-8"))
        cfg["workbook"] = str(wb) if cfg["workbook"].startswith("..") else cfg["workbook"]  # keep the abc source outside the temp copy, read-only
        mutate(cfg)
        (dest / "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
        out = tmp / "outputs"
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_pipeline.py"), base, month, "--clients-root", str(clients),
                            "--outputs-root", str(out)], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
        manifests = sorted((out / base).glob("manifest_*.json")) if (out / base).is_dir() else []
        stage, error = None, None
        if manifests:
            m = json.loads(manifests[-1].read_text(encoding="utf-8"))
            failed = [s for s in m.get("stages", []) if s["status"] == "failed"]
            if failed:
                stage, error = failed[0]["name"], failed[0].get("error")
        warnings = None
        sj = out / base / "summary.json"
        if sj.is_file():
            warnings = json.loads(sj.read_text(encoding="utf-8")).get("warnings", [])
        text = (p.stdout + p.stderr).strip().splitlines()
        first = error or (text[-1] if text else "")
        first = first.replace(str(tmp), "<tmp>").replace(str(ROOT), "<repo>")  # hide machine-specific folders
        first = re.sub(r"C:.{0,80}?Temp.[\w-]+", "<tmp>", first)  # the same temp folder in its long (non-8.3) spelling
        first = re.sub(r"C:.{0,60}?(?=[\w-]+\.xlsx)", "", first)
        return {"id": cid, "client": base, "field": field, "change": desc, "exit": p.returncode, "stopped_at": stage,
                "message": " ".join(first.split())[:230], "warnings": len(warnings) if warnings is not None else None,
                "warning_sample": (warnings or [""])[-1][:160] if warnings else None}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    results = [run_case(c) for c in CASES]
    RESULTS.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    for r in results:
        print(f"{r['id']:26} exit={r['exit']} stage={r['stopped_at']} warnings={r['warnings']}  {r['message'][:90]}")
    base = results[0]
    return 0 if base["exit"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
