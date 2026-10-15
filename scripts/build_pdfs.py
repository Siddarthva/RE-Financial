#!/usr/bin/env python3
"""Build the seven submission PDFs in 00_START_HERE/ from Markdown.

    python scripts/build_pdfs.py            # build all seven, then verify
    python scripts/build_pdfs.py --only 04  # build and verify one PDF

Pipeline: Markdown -> HTML (one shared print stylesheet) -> PDF through headless
Edge or Chrome driven by Playwright. Mermaid diagrams are rendered to inline SVG
in the browser before printing, so no diagram is left as code.

Setup (once):
    pip install -r scripts/requirements-pdf.txt
    npm install --prefix scripts/.pdf_cache mermaid@10.9.3

Numbers in the authored pages (00-03) are not typed by hand: {{placeholders}} are
filled from the newest "## Result:" section of 03_evals/FINAL_RUN.md, so the PDFs
cannot drift from the run record. --verify also checks this.
"""
from __future__ import annotations

import argparse
import html
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "00_START_HERE"
SRC = ROOT / "scripts" / "pdf_src"
CACHE = ROOT / "scripts" / ".pdf_cache"
MERMAID_JS = CACHE / "node_modules" / "mermaid" / "dist" / "mermaid.min.js"
FINAL_RUN = ROOT / "03_evals" / "FINAL_RUN.md"
SUBTITLE = "Submission for the RE Financial Services build exercise"

ARCH = ROOT / "04_architecture"
WORKFLOWS = ARCH / "workflows"
ROBUST = ROOT / "03_evals" / "robustness" / "ROBUSTNESS_REPORT.md"

# name, title, sources, options. A source is a path, or ("note", text).
DOCS = [
    ("00_Submission_Overview", "Submission Overview", [SRC / "00_submission_overview.md"], {}),
    ("01_Connection_Architecture", "Connection Architecture", [SRC / "01_connection_architecture.md"], {}),
    ("02_Skill_and_Analysis_Workflow", "Skill and Analysis Workflow", [SRC / "02_skill_and_analysis_workflow.md"], {}),
    ("03_Evals_and_Regression", "Evals and Regression", [SRC / "03_evals_and_regression.md"], {}),
    ("04_Architecture_OnePage", "Architecture (one page)", [ARCH / "architecture.md"], {"one_page": True}),
    (
        "05_Workflows_Appendix",
        "Workflows Appendix",
        [("note", "Appendix — supplementary to the one-page note"), ARCH / "workflow.md", WORKFLOWS / "README.md"]
        + sorted(WORKFLOWS.glob("[a-g]_*.md")),
        {"appendix": True},
    ),
    (
        "06_Verification_and_Robustness_Report",
        "Verification and Robustness Report",
        [ARCH / "verification_matrix.md", ROBUST],
        {"dated": True},
    ),
]

CSS = """
:root { --fs: 11pt; }
@page { size: A4; }
* { box-sizing: border-box; }
body { font-family: "Segoe UI", Arial, Helvetica, sans-serif; font-size: var(--fs); line-height: 1.38;
       color: #222; margin: 0; }
h1 { font-size: 1.7em; margin: 0 0 .5em; padding-bottom: .2em; border-bottom: 2px solid #555; break-before: page; }
body > h1:first-child, body > .doc-note + h1 { break-before: auto; }
h2 { font-size: 1.22em; margin: 1.1em 0 .35em; color: #333; break-after: avoid; }
h3 { font-size: 1.05em; margin: .9em 0 .3em; color: #333; break-after: avoid; }
p { margin: .45em 0; } ul, ol { margin: .35em 0; padding-left: 1.4em; } li { margin: .12em 0; }
code { font-family: Consolas, "Courier New", monospace; font-size: .88em; background: #f1f1f1; padding: 0 .2em;
       border-radius: 2px; overflow-wrap: anywhere; }
pre { background: #f6f6f6; border: 1px solid #ddd; padding: .5em .7em; font-size: .85em; white-space: pre-wrap;
      overflow-wrap: anywhere; break-inside: avoid; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: .6em 0; font-size: .88em; }
th, td { border: 1px solid #bbb; padding: .25em .45em; vertical-align: top; text-align: left; overflow-wrap: break-word; }
th { background: #ececec; } thead { display: table-header-group; } tr { break-inside: avoid; }
table.wide { font-size: .68em; } table.wide th, table.wide td { padding: .15em .25em; }
blockquote { margin: .6em 0; padding: .1em .8em; border-left: 3px solid #999; color: #444; background: #f7f7f7; }
a, .ref { color: inherit; text-decoration: none; }
hr { border: 0; border-top: 1px solid #ccc; margin: 1em 0; }
figure.diagram { margin: .8em 0; text-align: center; break-inside: avoid; }
figure.diagram svg { max-width: 100%; max-height: 165mm; width: auto; height: auto; }
.doc-note { font-size: .95em; font-weight: 600; color: #444; border: 1px solid #999; padding: .3em .6em;
            margin: 0 0 .8em; display: inline-block; }
.src-note { font-size: .85em; color: #555; margin: -.3em 0 .6em; }
"""


# ---------------------------------------------------------------- run record

def final_run_values() -> dict[str, str]:
    """Placeholders from the newest '## Result:' table in FINAL_RUN.md."""
    text = FINAL_RUN.read_text(encoding="utf-8")
    m = re.search(r"^## Result:[^\n]*?(\d{4}-\d{2}-\d{2})[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not m:
        sys.exit("FINAL_RUN.md has no '## Result:' section")
    rows = {}
    for line in m.group(2).splitlines():
        cells = [c.strip().replace("**", "") for c in line.strip().strip("|").split("|")]
        if len(cells) == 3 and cells[0] not in ("Check", "---"):
            rows[cells[0].lower()] = (cells[1], cells[2])

    def row(prefix: str) -> tuple[str, str]:
        for k, v in rows.items():
            if k.startswith(prefix):
                return v
        sys.exit(f"FINAL_RUN.md newest section has no '{prefix}' row")

    unit, golden, mut, fault, scan = (row(p) for p in ("unit", "golden", "mutation", "robustness", "secret"))
    first_int = lambda s: re.search(r"\d+", s).group(0)  # noqa: E731
    src = lambda name: re.search(rf"{name} (\d+)", golden[1]).group(1)  # noqa: E731
    return {
        "final_run_date": m.group(1),
        "unit": first_int(unit[1]), "unit_result": unit[1],
        "golden": re.search(r"(\d+)/(\d+)", golden[1]).group(2), "golden_result": golden[1].split(" (")[0],
        "g_wb": re.search(r"workbook (\d+)", golden[1]).group(1),
        "g_pert": src(r"workbook\+perturbation"), "g_cell": src("ABC cell-sourced"),
        "mut": re.search(r"(\d+)/(\d+)", mut[1]).group(2), "mut_result": re.search(r"\d+/\d+ caught", mut[1]).group(0),
        "fault": re.search(r"(\d+)/(\d+)", fault[1]).group(2), "fault_result": fault[1],
        "scan_files": re.search(r"(\d+) text files", scan[1]).group(1),
        "scan_result": f"{scan[1]}",
    }


def fill_placeholders(md: str, values: dict[str, str]) -> str:
    def sub(m: re.Match) -> str:
        if m.group(1) not in values:
            sys.exit(f"unknown placeholder {{{{{m.group(1)}}}}}")
        return values[m.group(1)]
    return re.sub(r"\{\{(\w+)\}\}", sub, md)


# ------------------------------------------------------------------ markdown

def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def md_to_html(md: str) -> str:
    import markdown
    body = markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists"])
    # Mermaid fences -> diagram holders rendered by the browser.
    # Left-to-right flowcharts are unreadably small on a portrait page, so they print top-to-bottom.
    body = re.sub(
        r'<pre><code class="language-mermaid">(.*?)</code></pre>',
        lambda m: '<figure class="diagram"><pre class="mermaid">'
                  + re.sub(r"\A(\s*flowchart )LR\b", r"\g<1>TB", m.group(1)) + "</pre></figure>",
        body, flags=re.S)
    # Relative links point at repo files that do not exist in a PDF: keep the text only.
    body = re.sub(r'<a href="(?!https?://)[^"]*">(.*?)</a>', r'<span class="ref">\1</span>', body, flags=re.S)
    body = body.replace("✅", "Pass").replace("❌", "FAIL")
    # Wide tables get a smaller font.
    def mark_wide(m: re.Match) -> str:
        return '<table class="wide">' if m.group(0).count("<th") >= 7 else "<table>"
    body = re.sub(r"<table>(?:(?!</thead>).)*</thead>", lambda m: mark_wide(m) + m.group(0)[7:], body, flags=re.S)
    return body


def file_date(path: Path) -> str:
    return git("log", "-1", "--format=%cs", "--", str(path.relative_to(ROOT))) or "uncommitted"


def assemble(sources: list, opts: dict, values: dict[str, str]) -> str:
    parts = []
    for s in sources:
        if isinstance(s, tuple):
            parts.append(f'<div class="doc-note">{html.escape(s[1])}</div>')
            continue
        md = fill_placeholders(s.read_text(encoding="utf-8"), values)
        h = md_to_html(md)
        if opts.get("dated"):
            rel = s.relative_to(ROOT).as_posix()
            note = f'<p class="src-note">Source: {rel}; last changed {file_date(s)}.</p>'
            h = re.sub(r"(</h1>)", r"\1" + note, h, count=1)
        parts.append(h)
    return "\n".join(parts)


def page_html(title: str, body: str) -> str:
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"<style>{CSS}</style></head><body>{body}</body></html>")


# ------------------------------------------------------------------- browser

def launch(pw):
    for channel in ("msedge", "chrome"):
        try:
            return pw.chromium.launch(channel=channel)
        except Exception:  # noqa: BLE001 - try the next browser
            continue
    sys.exit("Neither Edge nor Chrome could be launched by Playwright")


def render(browser, name: str, title: str, body: str, opts: dict, sha: str, date: str) -> tuple[Path, int, float]:
    from pypdf import PdfReader
    html_path = CACHE / "html" / f"{name}.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(page_html(title, body), encoding="utf-8")
    page = browser.new_page()
    page.goto(html_path.as_uri())
    n_diagrams = page.locator("pre.mermaid").count()
    if n_diagrams:
        page.add_script_tag(path=str(MERMAID_JS))
        errors = page.evaluate("""async () => {
            mermaid.initialize({startOnLoad: false, theme: 'neutral', securityLevel: 'strict',
                                fontFamily: 'Segoe UI, Arial, sans-serif',
                                flowchart: {useMaxWidth: true, htmlLabels: true}, sequence: {useMaxWidth: true, mirrorActors: false}});
            const errs = [];
            const nodes = [...document.querySelectorAll('pre.mermaid')];
            for (const [i, n] of nodes.entries()) {
                try { await mermaid.run({nodes: [n]}); }
                catch (e) { errs.push('diagram ' + (i + 1) + ': ' + (e.str || e.message || JSON.stringify(e))); }
            }
            return errs;
        }""")
        if errors:
            sys.exit(f"{name}: " + " | ".join(errors))
        done = page.locator("pre.mermaid svg").count()
        bad = page.locator("pre.mermaid", has_text="Syntax error").count()
        if done != n_diagrams or bad:
            sys.exit(f"{name}: {done}/{n_diagrams} diagrams rendered, {bad} with errors")
    header = (f'<div style="font-size:8px;width:100%;padding:0 18mm;color:#555;font-family:Segoe UI,Arial,sans-serif;">'
              f'{html.escape(SUBTITLE)} &mdash; {html.escape(title)}</div>')
    footer = (f'<div style="font-size:8px;width:100%;padding:0 18mm;color:#555;font-family:Segoe UI,Arial,sans-serif;'
              f'display:flex;justify-content:space-between;"><span>{html.escape(sha)} &middot; {html.escape(date)}</span>'
              f'<span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>')
    sizes = [11, 10.5, 10, 9.5, 9] if opts.get("one_page") else [11]
    pdf_path = OUT / f"{name}.pdf"
    for fs in sizes:
        page.evaluate(f"document.documentElement.style.setProperty('--fs', '{fs}pt')")
        page.pdf(path=str(pdf_path), format="A4", print_background=True, display_header_footer=True,
                 header_template=header, footer_template=footer,
                 margin={"top": "18mm", "bottom": "16mm", "left": "18mm", "right": "18mm"})
        pages = len(PdfReader(pdf_path).pages)
        if pages == 1 or not opts.get("one_page"):
            break
    page.close()
    return pdf_path, n_diagrams, fs


# -------------------------------------------------------------------- verify

RAW_SYNTAX = ["```", "flowchart ", "sequenceDiagram", "-->", "|---|", "**", "##", "<br"]
STALE = ["102 run", "18/18", "17/17", "103 run"]  # superseded counts; allowed only in the dated report (06)


def verify(results: dict[str, tuple[Path, int, float]], values: dict[str, str]) -> bool:
    import pypdfium2 as pdfium
    from pypdf import PdfReader
    ok = True
    (CACHE / "png").mkdir(parents=True, exist_ok=True)
    print(f"\n{'PDF':42} {'pages':>5} {'diagrams':>8}  checks")
    for name, (path, n_diag, fs) in results.items():
        reader = PdfReader(path)
        text = " ".join((p.extract_text() or "") for p in reader.pages)
        flat = re.sub(r"\s+", " ", text)
        problems = []
        if name.startswith("04") and len(reader.pages) != 1:
            problems.append(f"one-pager is {len(reader.pages)} pages")
        if re.search(r"\{\{\w+\}\}", text):
            problems.append("unfilled {{placeholder}}")
        for tok in RAW_SYNTAX:
            if tok in text:
                problems.append(f"raw syntax {tok!r}")
        if name[:2] in ("00", "01", "02", "03"):
            problems += [f"stale count {t!r}" for t in STALE if t in flat]
        if name.startswith("00"):
            for need in (values["unit_result"], values["golden_result"], values["mut_result"], values["fault_result"]):
                if need not in flat:
                    problems.append(f"missing run-record value {need!r}")
        if name.startswith("04") and "Architecture (one page)" not in flat:
            problems.append("note text missing")
        pdf = pdfium.PdfDocument(str(path))
        pdf[0].render(scale=1.3).to_pil().save(CACHE / "png" / f"{name}.png")
        note = "ok" if not problems else "; ".join(problems)
        extra = f" (font {fs}pt)" if name.startswith("04") else ""
        print(f"{name:42} {len(reader.pages):>5} {n_diag:>8}  {note}{extra}")
        ok &= not problems
    print(f"\nPage 1 of each PDF rasterised to {(CACHE / 'png').relative_to(ROOT).as_posix()}/")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="build just the PDF whose name starts with this prefix, e.g. 04")
    args = ap.parse_args()
    if not MERMAID_JS.exists():
        sys.exit(f"mermaid not installed: run  npm install --prefix scripts/.pdf_cache mermaid@10.9.3")
    from playwright.sync_api import sync_playwright
    values = final_run_values()
    sha = git("rev-parse", "--short", "HEAD") + ("+uncommitted" if git("status", "--porcelain") else "")
    date = git("log", "-1", "--format=%cs")
    docs = [d for d in DOCS if not args.only or d[0].startswith(args.only)]
    if not docs:
        sys.exit(f"no PDF matches {args.only!r}")
    OUT.mkdir(exist_ok=True)
    results = {}
    with sync_playwright() as pw:
        browser = launch(pw)
        for name, title, sources, opts in docs:
            results[name] = render(browser, name, title, assemble(sources, opts, values), opts, sha, date)
            print(f"built {name}.pdf")
        browser.close()
    return 0 if verify(results, values) else 1


if __name__ == "__main__":
    sys.exit(main())
