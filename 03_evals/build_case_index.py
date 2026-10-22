"""Write 03_evals/CASE_INDEX.md: one row per golden case, computed from the real files, not typed by hand.

    python 03_evals/build_case_index.py

Inputs (all read-only): golden_cases.json (the case, its source cells, its perturbation), outputs/mutation_report.md
(which mutants each case caught, from the last `mutation_test.py` run) and outputs/robustness_results.json (the fault
suite's last run). Run `python 03_evals/mutation_test.py` first if the mutation report is stale.

"Why it matters" is the one authored column: one sentence per case TYPE, kept in WHY below. Everything else
(source, what it tests, mutants, faults) comes from the files.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "03_evals" / "golden_cases.json"
MUTATION = ROOT / "outputs" / "mutation_report.md"
FAULTS = ROOT / "outputs" / "robustness_results.json"
OUT = ROOT / "03_evals" / "CASE_INDEX.md"

WHY = {
    "source_fields": "A non-wide source (QuickBooks JSON or a long-format sheet) must give the same packet number as the hand calculation from its named fields/cells",
    "revenue_mom": "The headline movement an owner reads first; a wrong sign or base misleads every sentence built on it.",
    "gross_margin": "Margin is the ratio most often quoted; the denominator must be revenue, not cost.",
    "ttm": "A trailing-twelve-month figure over fewer or gapped months looks valid and is not.",
    "duplicate_month": "Two columns for one month would double-count it without any visible error.",
    "missing_revenue": "With no revenue row every margin is meaningless; the run must refuse, not return zeros.",
    "expense_category": "Category trends are where owners look for what changed in spend.",
    "zero_prior_revenue": "Dividing by a zero prior month must give 'undefined', never infinity or a made-up percent.",
    "short_history_commentary": "Commentary must say TTM is not available instead of quoting a partial year.",
    "abc_seasonal_peak": "Stops the commentary calling a repeating February peak a one-month problem.",
    "abc_one_off": "One-offs distort margins, TTM and net income; they must be named and separable.",
    "abc_first_ttm": "Pins the first month a TTM is legitimate, including the Dec 2025 one-offs inside it.",
    "abc_opex_spike": "Spikes from a zero base need a null percent, and one-offs must not be called recurring.",
    "abc_latest_summary": "The full June 2026 summary every number in the commentary is graded against.",
    "month_labels": "Mid-month dates must normalise to the 1st without moving a value to another month.",
    "abc_line_item_step": "A step change that persists is not a one-off; the engine must not treat it as one.",
    "abc_line_item_value": "A negative reversal after a zero month keeps its sign and has no percent.",
    "abc_cash_runway": "Runway is the owner-facing risk number; it must come from Balance Sheet cash, not net income.",
    "abc_margin_flags": "The config threshold must flag exactly the months that fell more than 5 pp and no others.",
    "intake_gate": "Bad input must stop the close with a message naming the cause; a silent success would carry wrong numbers into the pack.",
    "flux_item": "Each flagged movement must carry the right amounts, source cells and reason code for the reviewer.",
    "skill_text": "Skill-written text is graded against the engine's JSON, so an invented or mistyped number fails.",
    "yoy_view": "A year-over-year view must compare the same month a year earlier, not the previous month.",
    "adjusted_net_income": "Removing one-offs must add costs back with the right sign.",
    "commentary_sections": "The reviewer relies on the seven sections being present and in order.",
}


def source_text(c: dict) -> str:
    src, cells = c["source"], None
    if isinstance(src, dict) and src.get("kind") in ("qbo", "long"):
        items = src.get("fields") or src.get("cells") or []
        label = "QuickBooks JSON, hand-computed" if src["kind"] == "qbo" else "Long-format workbook (c08), hand-computed"
        refs = [f"{f['row']} {f['column']}" if "row" in f else f"{f['sheet']}!{f['cell']}" for f in items]
        return label + f" ({', '.join(refs)})"
    if isinstance(src, dict):
        label = f"{src.get('sheet', 'workbook')}, hand-computed"
        cells = src.get("cells")
    else:
        label = {"workbook": "Workbook", "workbook+perturbation": "Workbook + perturbed copy"}.get(src, src)
        label += f", {c.get('sheet', 'Income Statement')}" if c.get("sheet") else ""
        cells = c.get("source_cells")
    refs = []
    if isinstance(cells, dict):
        refs = [str(v) if not isinstance(v, (int, float)) else str(k) for k, v in cells.items()]
    elif isinstance(c.get("input"), dict) and c["input"].get("revenue_row") and c["input"].get("columns"):
        refs = [f"{col}{c['input']['revenue_row']}" for col in c["input"]["columns"] if re.fullmatch(r"[A-Z]{1,2}", str(col))]
    refs = refs[:5] + (["..."] if len(refs) > 5 else [])
    return label + (f" ({', '.join(refs)})" if refs else "")


def mutants_by_case() -> dict:
    out: dict[str, list[str]] = {}
    for line in MUTATION.read_text(encoding="utf-8").splitlines():
        cells = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[2].endswith("yes"):
            for gid in re.findall(r"\bG\d\d\b", cells[3]):
                out.setdefault(gid, []).append(f"{cells[0]} ({cells[1].strip('`')})")
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    mut = mutants_by_case()
    total = sum(1 for l in MUTATION.read_text(encoding="utf-8").splitlines() if re.match(r"\|[^|]+\|[^|]+\|\s*(✅|❌)", l))
    results = json.loads(FAULTS.read_text(encoding="utf-8"))["results"]
    stricter = [r["id"] for r in results if r.get("stricter")]
    lines = ["# Golden case index", "",
             "Generated by `python 03_evals/build_case_index.py` from `golden_cases.json`, `outputs/mutation_report.md` (last full mutation run) "
             "and `outputs/robustness_results.json` (last fault run). Do not edit by hand. Only the **Why it matters** column is authored, "
             "one sentence per case type.", "",
             f"{len(cases)} cases; {total} mutants in the report. A mutant is listed against a case only if the report names that case among "
             "those that failed it. The fault suite is a separate harness (`robustness/fault_injection.py`); a fault is listed against a case "
             "only where the case itself names it, or, for G24, the faults whose run records its Current Year Earnings refusal.", "",
             "| Case | Source | What it tests | Why it matters | Mutants it catches | Faults |", "|---|---|---|---|---|---|"]
    uncaught = []
    for c in cases:
        hits = mut.get(c["id"], [])
        if not hits:
            uncaught.append(c["id"])
        fault_ids = sorted(set(re.findall(r"[Ff]ault[s]? (F\d\d)", json.dumps(c))))
        if c["id"] == "G24":  # the six stricter faults are refused on the Current Year Earnings check
            fault_ids = sorted(set(fault_ids) | set(stricter))
        what = c["name"] + (f". {c['perturbation']['purpose']}" if isinstance(c.get("perturbation"), dict) and c["perturbation"].get("purpose")
                            and c["source"] == "workbook+perturbation" else "")
        esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {c['id']} | {esc(source_text(c))} | {esc(what)} | {WHY[c['type']]} | "
                     f"{esc('; '.join(hits)) if hits else 'none in this mutant set'} | {', '.join(fault_ids) or 'none named'} |")
    lines += ["", f"Cases that catch no mutant in the {total}-mutant set: {', '.join(uncaught) or 'none'}. "
              "That is not necessarily a gap: the mutant set targets engine arithmetic, and these cases pin refusals, perturbed inputs "
              "and skill-text grading. Whether another test or fault covers them is not computed here."]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(cases)} cases, {total} mutants, {len(uncaught)} cases catch none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
