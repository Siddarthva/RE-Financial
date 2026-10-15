"""Fault injection: does the pipeline ever produce a successful run with wrong numbers and no warning?

    python 03_evals/robustness/fault_injection.py            # all faults -> ROBUSTNESS_REPORT.md
    python 03_evals/robustness/fault_injection.py F12 F26    # selected faults only (report not rewritten)

For each fault this writes a corrupted COPY of the ABC workbook into a fresh temp folder, with a copy of
clients/abc/config.yaml pointing at it, and runs `scripts/run_pipeline.py abc 2026-06 --clients-root ...
--outputs-root ...` there. The source workbook is only read (its SHA-256 is checked before and after), and
nothing under clients/ or outputs/ is written.

Every fault declares its REQUIRED behaviour before it runs:
  STOP   the pipeline fails at Intake, the message contains `expect` (the cell, sheet or cause), and no
         review packet is written;
  WARN   the run succeeds and a data-quality warning containing `expect` is in the review packet (which feeds
         the sign-off pack's Open Questions) and in the analysis workbook's Data Quality sheet;
  HANDLE the run succeeds with no new warning, every number in the review packet equals the baseline, and so does
         every account amount in the analysis workbook (its Account Values sheet).
A run that succeeds with numbers different from the baseline and no warning is SILENT-WRONG, the one outcome
that must never happen.

The baseline is the same workbook saved by openpyxl with values only (no formulas), which every fault starts
from; it is checked against the committed outputs/abc/review_packet_2026-06.json first.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data" / "ABC Inc - Financial Statements.xlsx"
SOURCE_SHA = "75da8d679a89551f9e46b3563b7cfc724d9aaeabe0444b0214d455a0b335a0ea"
CONFIG = ROOT / "clients" / "abc" / "config.yaml"
PIPELINE = ROOT / "scripts" / "run_pipeline.py"
REPORT = Path(__file__).resolve().parent / "ROBUSTNESS_REPORT.md"
RESULTS = ROOT / "outputs" / "robustness_results.json"
CLIENT, MONTH = "abc", "2026-06"
IS, BS = "Income Statement", "Balance Sheet"
TIEOUT_STOP = "Current Year Earnings = year-to-date net income"
CORE = ("latest_month", "prior_month", "months", "line_items", "top_movements", "cash", "gross_margin_flags", "one_offs")


# ---------------------------------------------------------------- workbook helpers (values-only copy)

def header_row(ws) -> int:
    return next(r for r in range(1, 20) if "Account" in [str(c.value) for c in ws[r]])


def month_col(ws, label: str) -> int:
    """Column index of a month header such as 'Jun 2026' on the Income Statement."""
    hr = header_row(ws)
    return next(c.column for c in ws[hr] if c.value == label)


def row_of(ws, label: str) -> int:
    for r in range(header_row(ws) + 1, ws.max_row + 1):
        for c in (1, 2):
            v = ws.cell(r, c).value
            if v is not None and str(v).strip() == label:
                return r
    raise KeyError(label)


SECTION_TOTAL = {"income": "Total Income", "cogs": "Total Cost of Goods Sold", "opex": "Total Operating Expenses"}
# How a +1 change in a detail line of each section moves the summary rows, so a perturbed copy still foots.
KNOCK_ON = {"income": {"Gross Profit": 1, "Operating Income": 1, "Net Income": 1},
            "cogs": {"Gross Profit": -1, "Operating Income": -1, "Net Income": -1},
            "opex": {"Operating Income": -1, "Net Income": -1}}


def bump(ws, account: str, section: str, month: str, delta: float):
    """Add delta to a detail cell and to every total that depends on it (the copy stays internally consistent)."""
    col = month_col(ws, month)
    for label, sign in [(account, 1), (SECTION_TOTAL[section], 1)] + list(KNOCK_ON[section].items()):
        cell = ws.cell(row_of(ws, label), col)
        cell.value = (cell.value or 0) + sign * delta


def value(ws, account: str, month: str):
    return ws.cell(row_of(ws, account), month_col(ws, month)).value


def coord(ws, account: str, month: str) -> str:
    return ws.cell(row_of(ws, account), month_col(ws, month)).coordinate


# ---------------------------------------------------------------- faults

@dataclass
class Fault:
    fid: str
    family: str
    name: str
    required: str            # STOP / WARN / HANDLE
    expect: str              # substring of the STOP message or WARN warning ("" for HANDLE)
    mutate: Callable | None = None   # (workbook, ctx) -> None; edits the values-only copy
    raw: Callable | None = None      # (path) -> None; writes the file itself (corrupt, formulas)
    lock: bool = False
    touches: tuple | None = None     # variants only: the detail accounts the fault itself changes; all others must equal the baseline


def _drop_month(label):
    def f(wb, ctx):
        wb[IS].delete_cols(month_col(wb[IS], label))
    return f


def _dup_month(wb, ctx):
    ws = wb[IS]
    c = month_col(ws, "Jun 2026")
    ws.insert_cols(c + 1)
    for r in range(1, ws.max_row + 1):
        ws.cell(r, c + 1).value = ws.cell(r, c).value


def _shuffle_months(wb, ctx):
    ws = wb[IS]
    hr = header_row(ws)
    cols = [c.column for c in ws[hr] if c.column > 2 and c.value]
    block = [[ws.cell(r, c).value for c in cols] for r in range(1, ws.max_row + 1)]
    order = cols[::2] + cols[1::2]  # interleave: no longer newest-first
    for r, vals in enumerate(block, start=1):
        for target, src in zip(cols, order):
            ws.cell(r, target).value = vals[cols.index(src)]


def _blank_col(wb, ctx):
    wb[IS].insert_cols(month_col(wb[IS], "Mar 2026") + 1)


def _blank_rows(wb, ctx):
    wb[IS].insert_rows(row_of(wb[IS], "Bonus"), 2)


def _shift_header(wb, ctx):
    wb[IS].insert_rows(1, 3)


def _rename_sheet(wb, ctx):
    wb[IS].title = "P&L"


def _drop_bs(wb, ctx):
    del wb[BS]


def _extra_sheet(wb, ctx):
    wb.create_sheet("Notes")["A1"] = "Prepared by finance; unaudited."


def _merge_header(wb, ctx):
    ws = wb[IS]
    c, hr = month_col(ws, "Jun 2026"), header_row(ws)
    ws.merge_cells(start_row=hr, start_column=c, end_row=hr, end_column=c + 1)


def _set(account, month, text):
    def f(wb, ctx):
        ctx["cell"] = coord(wb[IS], account, month)
        wb[IS][ctx["cell"]].value = text
    return f


def _blank_cell(wb, ctx):
    ws = wb[IS]
    bump(ws, "Bonus", "opex", "Feb 2026", -value(ws, "Bonus", "Feb 2026"))  # totals as if the line were zero
    ws[coord(ws, "Bonus", "Feb 2026")].value = None


def _money_text(account, month, neg=False):
    def f(wb, ctx):
        ws = wb[IS]
        v = value(ws, account, month)
        assert round(v, 2) == v and (v < 0) == neg, (account, month, v)
        ws[coord(ws, account, month)].value = f"({abs(v):,.2f})" if neg else f"${v:,.2f}"
    return f


def _outlier(wb, ctx):
    ws = wb[IS]
    bump(ws, "Usage Fees", "income", "Jun 2026", value(ws, "Usage Fees", "Jun 2026") * 999)


def _zero_revenue(wb, ctx):
    ws = wb[IS]
    for a in ctx["income_lines"]:
        v = value(ws, a, "Jun 2026") or 0
        if v:
            bump(ws, a, "income", "Jun 2026", -v)


def _rename(old, new):
    def f(wb, ctx):
        ws = wb[IS]
        ws.cell(row_of(ws, old), 2 if ws.cell(row_of(ws, old), 2).value else 1).value = new
    return f


def _new_account(wb, ctx):
    ws = wb[IS]
    r = row_of(ws, "Total Operating Expenses")
    ws.insert_rows(r)
    ws.cell(r, 2).value = "Crypto Mining Costs"
    hr = header_row(ws)
    for c in ws[hr]:
        if c.column > 2 and c.value:
            ws.cell(r, c.column).value = 100.0
            for label, sign in [("Total Operating Expenses", 1), ("Operating Income", -1), ("Net Income", -1)]:
                cell = ws.cell(row_of(ws, label), c.column)
                cell.value += sign * 100.0


def _trailing_spaces(wb, ctx):
    ws = wb[IS]
    for r in range(header_row(ws) + 1, ws.max_row + 1):
        for c in (1, 2):
            v = ws.cell(r, c).value
            if isinstance(v, str):
                ws.cell(r, c).value = v + "  "


def _drop_row(label):
    def f(wb, ctx):
        wb[IS].delete_rows(row_of(wb[IS], label))
    return f


def _not_footing(wb, ctx):
    ws = wb[IS]
    ctx["cell"] = coord(ws, "Total Income", "Mar 2026")
    ws[coord(ws, "Usage Fees", "Mar 2026")].value += 1000.0  # line changes, totals do not


def _eleven_months(wb, ctx):
    ws = wb[IS]
    for label in ("Jul 2025", "Jun 2025", "May 2025", "Apr 2025", "Mar 2025", "Feb 2025", "Jan 2025"):
        ws.delete_cols(month_col(ws, label))


def _formulas_no_cache(path: Path):
    load_workbook(io.BytesIO(SOURCE.read_bytes()), data_only=False).save(path)  # openpyxl keeps formulas, drops cached values


def _corrupt(path: Path):
    path.write_bytes(b"This is not a workbook.\n" * 50)


def _truncated(path: Path):
    path.write_bytes(SOURCE.read_bytes()[:4000])


def _with_bs_tied(base_mutate):
    """Variant of a fault: apply it, then restate the Balance Sheet so the tie-out still passes. Current Year Earnings
    is reset to the (mutated) Income Statement's year-to-date net income for every month both sheets have (fiscal year
    = calendar year, clients/abc/config.yaml), and Retained Earnings takes the opposite change, so Total Equity and
    Total Liabilities and Equity are untouched and the sheet still balances. Only the BS tie-out is defeated; the data
    problem the original fault introduces is the same."""
    def f(wb, ctx):
        base_mutate(wb, ctx)
        ws, bs = wb[IS], wb[BS]
        hr, ni_row = header_row(ws), row_of(ws, "Net Income")
        ytd, running = {}, {}
        for c in sorted((c for c in ws[hr] if c.column > 2 and c.value), key=lambda c: datetime.strptime(str(c.value), "%b %Y")):
            d = datetime.strptime(str(c.value), "%b %Y")
            running[d.year] = running.get(d.year, 0.0) + (ws.cell(ni_row, c.column).value or 0.0)
            ytd[(d.year, d.month)] = running[d.year]
        def bs_row(label):  # Balance Sheet labels sit in column C
            return next(r for r in range(1, bs.max_row + 1) if str(bs.cell(r, 3).value).strip() == label)
        cye, re_ = bs_row("Current Year Earnings"), bs_row("Retained Earnings")
        for c in bs[header_row(bs)]:
            if c.column <= 3 or not c.value:
                continue
            d = c.value if isinstance(c.value, datetime) else datetime.strptime(str(c.value), "%d %b %Y")
            if (d.year, d.month) in ytd:
                delta = ytd[(d.year, d.month)] - bs.cell(cye, c.column).value
                bs.cell(cye, c.column).value += delta
                bs.cell(re_, c.column).value -= delta
    return f


FAULTS = [
    # Structure
    Fault("F01", "Structure", "Missing month column: prior month (May 2026) deleted", "STOP", "no column for 2026-05", _drop_month("May 2026")),
    Fault("F02", "Structure", "Missing month column: Sep 2025 deleted mid-history", "WARN", "Months missing from the source: Sep 2025", _drop_month("Sep 2025")),
    Fault("F03", "Structure", "Duplicated month (Jun 2026 column copied next to itself)", "STOP", "appears in more than one column", _dup_month),
    Fault("F04", "Structure", "Months out of order (columns interleaved)", "HANDLE", "", _shuffle_months),
    Fault("F05", "Structure", "Extra blank column inside the month columns", "STOP", "Month columns contiguous", _blank_col),
    Fault("F06", "Structure", "Extra blank rows inside the data", "HANDLE", "", _blank_rows),
    Fault("F07", "Structure", "Header row shifted down 3 rows", "HANDLE", "", _shift_header),
    Fault("F08", "Structure", "Income Statement sheet renamed to 'P&L'", "STOP", "Sheet 'Income Statement' not found", _rename_sheet),
    Fault("F09", "Structure", "Balance Sheet missing", "STOP", "Sheet 'Balance Sheet' not found", _drop_bs),
    Fault("F10", "Structure", "Extra unknown sheet", "HANDLE", "", _extra_sheet),
    Fault("F11", "Structure", "Merged header cells (Jun and May 2026)", "STOP", "header cells are merged", _merge_header),
    # Values
    Fault("F12", "Values", "Text 'n/a' in a numeric cell (Usage Fees, Jun 2026)", "STOP", "{cell}", _set("Usage Fees", "Jun 2026", "n/a")),
    Fault("F13", "Values", "Empty cell inside a series (Bonus, Feb 2026; totals treat it as zero)", "WARN", "blank cell(s)", _blank_cell),
    Fault("F14", "Values", "Amount as text '$1,234.56' (Platform Revenue, Jun 2026)", "HANDLE", "", _money_text("Platform Revenue", "Jun 2026")),
    Fault("F15", "Values", "Negative as text '(1,234.56)'", "HANDLE", "", None),  # cell chosen at run time
    Fault("F16", "Values", "Extreme outlier x1000 (Usage Fees, Jun 2026, totals consistent)", "WARN", "Possible outlier: Usage Fees", _outlier),
    Fault("F17", "Values", "Zero total revenue in Jun 2026 (division by zero)", "WARN", "Revenue is zero in Jun 2026", _zero_revenue),
    Fault("F18", "Values", "Text 'NaN' in a numeric cell (COGS line, Jun 2026)", "STOP", "{cell}", None),
    Fault("F19", "Values", "Excel error value '#DIV/0!' in a numeric cell (Bonus, Jun 2026)", "STOP", "{cell}", _set("Bonus", "Jun 2026", "#DIV/0!")),
    # Labels
    Fault("F20", "Labels", "Account renamed (Bonus -> Bonuses)", "WARN", "Unmapped OPEX account (reported under 'Unmapped'): Bonuses", _rename("Bonus", "Bonuses")),
    Fault("F21", "Labels", "New unmapped account (Crypto Mining Costs, totals consistent)", "WARN", "Unmapped OPEX account (reported under 'Unmapped'): Crypto Mining Costs", _new_account),
    Fault("F22", "Labels", "Trailing spaces on every label", "HANDLE", "", _trailing_spaces),
    Fault("F23", "Labels", "Unicode look-alike label (Bonus with a Greek omicron)", "WARN", "non-ASCII", _rename("Bonus", "B\u03bfnus")),
    Fault("F24", "Labels", "Missing section total row (Total Cost of Goods Sold deleted)", "STOP", "'Total Cost of Goods Sold'", _drop_row("Total Cost of Goods Sold")),
    Fault("F25", "Labels", "Missing block subtotal row (Total Marketing deleted)", "HANDLE", "", _drop_row("Total Marketing")),
    Fault("F26", "Labels", "Subtotal does not foot (+1,000 on Usage Fees, Mar 2026)", "STOP", "Total Income foots", _not_footing),
    # Coverage
    Fault("F27", "Coverage", "Only 11 months (Aug 2025 - Jun 2026)", "WARN", "TTM not available", _eleven_months),
    Fault("F28", "Coverage", "Saved with formulas but no cached values", "STOP", "formula cells have no saved value", raw=_formulas_no_cache),
    Fault("F29", "Coverage", "Corrupt file (not a zip)", "STOP", "Not a valid .xlsx workbook", raw=_corrupt),
    Fault("F30", "Coverage", "Truncated .xlsx (zip header, cut off)", "STOP", "Cannot open", raw=_truncated),
    Fault("F31", "Coverage", "File open and locked by another program", "STOP", "open or locked", lock=True),
    # .xlsx cannot store inf: openpyxl writes it and reads it back as an empty cell, so the line no longer foots.
    Fault("F32", "Values", "Float inf written into a numeric cell (Bonus, Jun 2026; lands as an empty cell)", "STOP",
          "Total Operating Expenses foots", _set("Bonus", "Jun 2026", float("inf"))),
]

# Variants of the six WARN faults that the Balance Sheet tie-out now refuses (the originals above run as STOP, "stricter").
# Each restates the Balance Sheet so the tie-out passes; the declared WARN is then the behaviour required end to end:
# the warning in summary.json, the review packet, the Data Quality sheet and the reviewer Excel's Open Questions, with
# every number other than the fault's own effect equal to the baseline.
_BY_ID = {f.fid: f for f in FAULTS}
FAULTS += [
    Fault(f"{o}b", _BY_ID[o].family, _BY_ID[o].name + " [Balance Sheet restated to tie out]", "WARN", _BY_ID[o].expect,
          _with_bs_tied(_BY_ID[o].mutate), touches=touched)
    for o, touched in (("F02", ()), ("F13", ("Bonus",)), ("F16", ("Usage Fees",)), ("F17", "INCOME"), ("F21", ()), ("F27", ()))
]


def _late_bind(ctx):
    """Faults whose target cell depends on the workbook's contents."""
    f15 = next(f for f in FAULTS if f.fid == "F15")
    acct = next(a for a in ctx["detail_lines"] if (ctx["values"].get((a, "Jun 2026")) or 0) < 0
                and round(ctx["values"][(a, "Jun 2026")], 2) == ctx["values"][(a, "Jun 2026")])
    f15.name, f15.mutate = f"Negative as text '(1,234.56)' ({acct}, Jun 2026)", _money_text(acct, "Jun 2026", neg=True)
    f18 = next(f for f in FAULTS if f.fid == "F18")
    cogs = next(a for a in ctx["cogs_lines"] if ctx["values"].get((a, "Jun 2026")))
    f18.name, f18.mutate = f"Text 'NaN' in a numeric cell ({cogs}, Jun 2026)", _set(cogs, "Jun 2026", "NaN")


# ---------------------------------------------------------------- running

def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def snapshot(wb) -> list:
    return [(ws.title, [[c.value for c in row] for row in ws.iter_rows()]) for ws in wb.worksheets]


def run_case(base_wb, fault: Fault | None, ctx: dict) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="re_fault_"))
    try:
        cdir = tmp / "clients" / CLIENT
        cdir.mkdir(parents=True)
        cfg = CONFIG.read_text(encoding="utf-8").splitlines()
        cfg = [("workbook: book.xlsx" if line.startswith("workbook:") else line) for line in cfg]
        (cdir / "config.yaml").write_text("\n".join(cfg) + "\n", encoding="utf-8")
        book = cdir / "book.xlsx"
        local = dict(ctx)  # a mutation may record the cell it changed under "cell"
        if fault and fault.raw:
            fault.raw(book)
        else:
            wb = load_workbook(io.BytesIO(base_wb), data_only=True)  # fresh copy (deepcopy breaks openpyxl styles)
            if fault and fault.mutate:
                before = snapshot(wb)
                fault.mutate(wb, local)
                if snapshot(wb) == before and not wb.worksheets[0].merged_cells.ranges:
                    raise AssertionError(f"{fault.fid}: the mutation changed nothing; fix the fault, not the expectation")
            wb.save(book)
        cell = local.get("cell")
        handle = None
        if fault and fault.lock:
            if sys.platform != "win32":
                return {"skipped": "file locking test needs Windows"}
            import msvcrt
            handle = open(book, "r+b")
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, book.stat().st_size)
        clients = str(tmp / "clients")
        commands = {  # both entry points that produce numbers: the pipeline, and the /monthly-analysis skill's step 1
            "pipeline": [sys.executable, str(PIPELINE), CLIENT, MONTH, "--clients-root", clients, "--outputs-root", str(tmp / "out_pipeline")],
            "skill": [sys.executable, "-c", "import sys; sys.path.insert(0, 'src'); import monthly_review as m; "
                      f"m.prepare({CLIENT!r}, {MONTH!r}, {clients!r}, {str(tmp / 'out_skill')!r})"],
        }
        procs = {}
        try:
            for kind, cmd in commands.items():
                procs[kind] = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, cwd=ROOT)
        finally:
            if handle:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, book.stat().st_size)
                handle.close()
        res = {"cell": cell, "pipeline": collect(tmp / "out_pipeline" / CLIENT, procs["pipeline"], manifest=True),
               "skill": collect(tmp / "out_skill" / CLIENT, procs["skill"], manifest=False)}
        if fault and fault.required == "WARN":  # end to end: build the reviewer Excel (sign-off pack) from each path's packet
            for kind, out in (("pipeline", "out_pipeline"), ("skill", "out_skill")):
                if res[kind]["status"] == "success":
                    res[kind]["reviewer_oq"] = reviewer_open_questions(clients, tmp / out)
        return res
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def reviewer_open_questions(clients: str, outputs: Path) -> list:
    """Build the reviewer Excel (monthly_review.build) over this run's packet, using the committed ABC commentary and
    reviewer verdict as fixed inputs (only the packet differs), and return the Open Questions sheet's question column."""
    code = ("import sys; sys.path.insert(0, 'src'); import monthly_review as m; "
            f"m.build({CLIENT!r}, {MONTH!r}, 'outputs/abc/commentary_2026-06.md', 'outputs/abc/review_2026-06.json', {clients!r}, {str(outputs)!r})")
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, cwd=ROOT)
    xlsx = outputs / CLIENT / f"monthly_review_{MONTH}.xlsx"
    if p.returncode or not xlsx.is_file():
        return [f"<reviewer Excel not built: {p.stderr.strip()[-200:]}>"]
    wbq = load_workbook(xlsx, read_only=True)
    rows = [str(r[2]) for r in wbq["Open Questions"].iter_rows(min_row=2, values_only=True) if r and r[2]]
    wbq.close()
    return rows


def collect(out: Path, proc, manifest: bool) -> dict:
    """Outcome of one entry point: success/failed, the message a user sees, the packet and the Data Quality sheet."""
    packet_path = out / f"review_packet_{MONTH}.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8")) if packet_path.is_file() else None
    dq, values, summary_warnings = [], {}, []
    if (out / "summary.json").is_file():
        summary_warnings = [str(w) for w in json.loads((out / "summary.json").read_text(encoding="utf-8")).get("warnings", [])]
    if (out / "analysis.xlsx").is_file():
        wbq = load_workbook(out / "analysis.xlsx", read_only=True)
        if "Data Quality" in wbq.sheetnames:
            dq = [str(r[0]) for r in wbq["Data Quality"].iter_rows(min_row=2, values_only=True) if r and r[0]]
        if "Account Values" in wbq.sheetnames:  # every parsed amount, not just the packet's chosen month
            rows = list(wbq["Account Values"].iter_rows(values_only=True))
            months = [str(h)[:7] for h in rows[0][1:]] if rows else []
            values = {str(r[0]): dict(zip(months, r[1:])) for r in rows[1:] if r and r[0] is not None}
        wbq.close()
    if manifest:
        found = sorted(out.glob("manifest_*.json")) if out.is_dir() else []
        m = json.loads(found[-1].read_text(encoding="utf-8")) if found else {}
        status, errors = m.get("status"), [s.get("error", "") for s in m.get("stages", []) if s.get("status") == "failed"]
    else:  # the skill's prepare step: an exception's last line is what Claude (and the user) sees
        status = "success" if proc.returncode == 0 else "failed"
        lines = [l for l in proc.stderr.strip().splitlines() if l.strip()]
        errors = [lines[-1]] if proc.returncode and lines else []
    return {"exit": proc.returncode, "status": status, "errors": errors, "packet": packet, "dq_sheet": dq, "values": values, "summary_warnings": summary_warnings,
            "stderr_tail": proc.stderr.strip()[-300:]}


def _round(node):
    if isinstance(node, float):
        return round(node, 6)  # the packet's own precision (monthly_review._num); removes 1e-15 float noise
    if isinstance(node, dict):
        return {k: _round(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_round(v) for v in node]
    return node


def core(packet: dict) -> dict:
    return _round({k: packet.get(k) for k in CORE})


def same_values(got: dict, base: dict) -> bool:
    """Every account amount in the analysis workbook equals the baseline. Rows may be absent only if they are
    'Total ...' subtotals (e.g. a deleted block subtotal); every detail account must be present."""
    if {a for a in base if not a.lower().startswith("total ")} - set(got):
        return False
    return all(_round(got[a]) == _round(base[a]) for a in base if a in got)


SUMMARY_ROWS = ("gross profit", "operating income", "net income")


def numbers_otherwise_correct(fault: Fault, r: dict, baseline: dict, ctx: dict) -> bool:
    """Variants: every detail-account amount (any month the run still has) equals the baseline except the accounts the
    fault itself changes, and the Balance Sheet cash in the packet is unchanged (the restated rows are not cash)."""
    touched = set(ctx["income_lines"] if fault.touches == "INCOME" else fault.touches)
    for acct, months in r["values"].items():
        if acct in touched or acct.lower().startswith("total ") or acct.lower() in SUMMARY_ROWS or acct not in baseline["values"]:
            continue
        if any(_round(v) != _round(baseline["values"][acct].get(m)) for m, v in months.items()):
            return False
    return _round(r["packet"].get("cash")) == _round(baseline["packet"].get("cash"))


def judge(fault: Fault, r: dict, cell: str | None, baseline: dict, ctx: dict | None = None) -> dict:
    expect = fault.expect.replace("{cell}", cell or "?")
    if r["status"] != "success":
        msg = " | ".join(r["errors"]) or r["stderr_tail"] or f"exit {r['exit']}"
        stopped = r["packet"] is None and r["exit"] != 0
        ok = fault.required == "STOP" and expect in msg and stopped
        # Stricter than declared: the Balance Sheet tie-out (added after this suite's declarations were fixed) refuses a
        # file whose net income no longer matches Current Year Earnings, before the declared WARN can happen. A refusal
        # is never SILENT-WRONG, so it passes, but it is counted and shown separately (the declaration is NOT edited).
        stricter = fault.required == "WARN" and stopped and TIEOUT_STOP in msg
        return {"actual": "STOP", "pass": ok or stricter, "message": msg, "stricter": stricter}
    new_warnings = [w for w in r["packet"].get("warnings", []) if w not in baseline["packet"]["warnings"]]
    same = core(r["packet"]) == core(baseline["packet"]) and same_values(r["values"], baseline["values"])
    if new_warnings:
        hit = next((w for w in new_warnings if expect and expect in w), None)
        ok = fault.required == "WARN" and hit is not None and any(expect in w for w in r["dq_sheet"])
        if ok and fault.fid.endswith("b"):  # variants: also summary.json and the reviewer Excel (checked for every WARN run below)
            ok = (any(expect in w for w in r["summary_warnings"]) and any(expect in q for q in r.get("reviewer_oq", []))
                  and numbers_otherwise_correct(fault, r, baseline, ctx))
        return {"actual": "WARN", "pass": ok, "message": hit or new_warnings[0], "numbers_equal_baseline": same}
    if same:
        return {"actual": "HANDLE", "pass": fault.required == "HANDLE", "message": "Run succeeded; every review-packet number and every account amount equals the baseline."}
    return {"actual": "SILENT-WRONG", "pass": False, "message": "Run succeeded with numbers that differ from the baseline and no warning."}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    sys.stdout.reconfigure(encoding="utf-8")
    before = sha256(SOURCE)
    if before != SOURCE_SHA:
        print(f"Source workbook hash is {before[:16]}..., expected {SOURCE_SHA[:16]}...; refusing to run.")
        return 2
    values_wb = load_workbook(io.BytesIO(SOURCE.read_bytes()), data_only=True)  # values only; the file itself is never opened for writing
    buf = io.BytesIO()
    values_wb.save(buf)
    base_wb = buf.getvalue()  # bytes of the values-only copy; every case starts from these
    sys.path.insert(0, str(ROOT / "src"))
    import abc_workbook_adapter as engine
    am = engine.parse_wide_income_statement(io.BytesIO(SOURCE.read_bytes()))
    sections = am.attrs["sections"]
    ws = values_wb[IS]
    ctx = {"income_lines": [a for a in am.index if sections.get(a) == "income"],
           "cogs_lines": [a for a in am.index if sections.get(a) == "cost of goods sold"],
           "detail_lines": [a for a in am.index if sections.get(a) and not a.lower().startswith("total")],
           "values": {(a, "Jun 2026"): value(ws, a, "Jun 2026") for a in am.index if sections.get(a)}}
    _late_bind(ctx)
    ctx.pop("values")

    print("Baseline (values-only copy, no fault) ...", flush=True)
    base = run_case(base_wb, None, ctx)
    committed = json.loads((ROOT / "outputs" / CLIENT / f"review_packet_{MONTH}.json").read_text(encoding="utf-8"))
    for kind in ("pipeline", "skill"):
        b = base[kind]
        if b["status"] != "success" or core(b["packet"]) != core(committed) or b["packet"]["warnings"] != committed["warnings"]:
            print(f"Baseline ({kind}) does not reproduce outputs/abc/review_packet_2026-06.json; fix that first.", b["errors"] or b["stderr_tail"])
            return 2
    baseline = base["pipeline"]
    if base["skill"]["values"] != baseline["values"] or not baseline["values"]:
        print("Baseline analysis workbooks differ between the two paths; fix that first.")
        return 2

    selected = [f for f in FAULTS if not argv or f.fid in argv]
    rows = []
    for f in selected:
        r = run_case(base_wb, f, ctx)
        if r.get("skipped"):
            row = {"actual": "SKIPPED", "skill_actual": "SKIPPED", "pass": None, "message": r["skipped"], "skill_message": ""}
        else:
            jp, js = judge(f, r["pipeline"], r["cell"], baseline, ctx), judge(f, r["skill"], r["cell"], baseline, ctx)
            row = {"actual": jp["actual"], "skill_actual": js["actual"], "pass": jp["pass"] and js["pass"],
                   "message": jp["message"], "skill_message": js["message"],
                   "stricter": bool(jp.get("stricter") and js.get("stricter"))}
        for k in ("message", "skill_message"):  # temp paths name the user's home folder; keep them out of the report
            row[k] = re.sub(r"[A-Za-z]:[\\/][^|'\"]*?re_fault_\w+", "<temp>", row[k])
        rows.append({"id": f.fid, "family": f.family, "fault": f.name, "required": f.required, **row})
        print(f"{f.fid} {f.required:<6} -> pipeline {row['actual']:<12} skill {row['skill_actual']:<12} "
              f"{'PASS' if row['pass'] else 'SKIP' if row['pass'] is None else 'FAIL'}  {row['message'][:110]}", flush=True)

    after = sha256(SOURCE)
    passed = sum(1 for r in rows if r["pass"])
    failed = [r for r in rows if r["pass"] is False]
    print(f"\n{passed}/{len(rows)} faults behaved as required; source workbook hash {'unchanged' if after == before else 'CHANGED'}.")
    if not argv:
        write_report(rows, before, after)
    return 0 if not failed and after == before else 1


def write_report(rows, before, after):
    esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")
    lines = ["# Robustness report: fault injection", "",
             "Generated by `python 03_evals/robustness/fault_injection.py` (do not edit by hand). Each fault is applied to a COPY of "
             "the ABC workbook in a temp folder, and both entry points that produce numbers run on that copy: `scripts/run_pipeline.py` "
             "(with `--clients-root/--outputs-root` pointing at the temp folder) and `monthly_review.prepare`, step 1 of the `/monthly-analysis` skill. "
             "A fault passes only if both paths behave as required.",
             "", f"Source workbook SHA-256 before `{before[:16]}…`, after `{after[:16]}…` ({'unchanged' if before == after else 'CHANGED'}).", "",
             "Required behaviour, fixed before running: **STOP** = intake refuses with a message naming the cell, sheet or cause, and no review "
             "packet is written; **WARN** = run continues and the warning is in the review packet (Open Questions in the sign-off pack) and in "
             "the analysis workbook's Data Quality sheet; **HANDLE** = run continues, no new warning, every review-packet number and every account amount in the analysis "
             "workbook (`Account Values` sheet) equals the baseline. **SILENT-WRONG** (success, different numbers, no warning) must never occur.", "",
             f"**Result: {sum(1 for r in rows if r['pass'])}/{len(rows)} pass; SILENT-WRONG: "
             f"{sum(1 for r in rows if 'SILENT-WRONG' in (r['actual'], r['skill_actual']))}.**", "",
             "**Stricter than declared:** a fault declared WARN that the Balance Sheet tie-out refuses (STOP) before the warning could happen. "
             "Passes because nothing wrong is accepted; the declarations were not edited. Before the tie-out existed (commit c8421e4) these ran as WARN. "
             "Rule: an expectation only moves toward stricter (HANDLE, WARN, STOP), never looser; no row moved looser. "
             f"Rows moved to STOP: {', '.join(r['id'] for r in rows if r.get('stricter')) or 'none'}. Per-fault reasons: `03_evals/evals_caught.md`.", "",
             "**WARN-path variants (F02b, F13b, F16b, F17b, F21b, F27b):** the same six faults with the Balance Sheet restated so the tie-out "
             "passes (Current Year Earnings reset to the mutated year-to-date net income, Retained Earnings takes the opposite change, so the "
             "sheet still balances and cash is unchanged). Required, declared in code before running: WARN end to end, i.e. the warning is in "
             "`summary.json`, the review packet, the analysis workbook's Data Quality sheet and the reviewer Excel's Open Questions (built by "
             "`monthly_review.build` over that run's packet), and every detail-account amount other than the accounts the fault itself changes "
             "equals the baseline, as does the packet's cash. The originals stay as STOP cases, so both the refusal and the warning path are covered.", "",
             "| ID | Family | Fault | Required | Pipeline | Skill path | Pass | Message shown (pipeline) |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        mark = "✅ (stricter)" if r.get("stricter") else "✅" if r["pass"] else "—" if r["pass"] is None else "❌"
        lines.append(f"| {r['id']} | {r['family']} | {esc(r['fault'])} | {r['required']} | {r['actual']} | {r['skill_actual']} | {mark} | {esc(r['message'][:400])} |")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    RESULTS.write_text(json.dumps({"source_sha256_unchanged": before == after, "results": rows}, indent=2), encoding="utf-8")
    print(f"Report: {REPORT}\nResults: {RESULTS}")


if __name__ == "__main__":
    sys.exit(main())
