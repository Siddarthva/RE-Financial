"""Check that every relative Markdown link in git-tracked .md files resolves.

Usage: python scripts/check_links.py [file.md ...]   (default: every git-tracked .md)
Checks the target file or folder exists and, for `file.md#anchor`, that the anchor matches a heading.
External (http/https/mailto) links are not fetched. Links inside code fences and inline code are ignored.
Exit 0 when every link resolves, 1 otherwise.
"""
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)|!\[[^\]]*\]\(([^)\s]+)\)")


def slug(heading: str) -> str:
    """GitHub-style anchor: lowercase, drop punctuation except hyphens, spaces to hyphens."""
    text = re.sub(r"[`*_]", "", heading.strip().lower())
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    out, fence = set(), False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
        elif not fence and (m := re.match(r"#{1,6}\s+(.*)", line)):
            out.add(slug(m.group(1)))
    return out


def links(path: Path):
    fence = False
    for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        line = re.sub(r"`[^`]*`", "", line)
        for m in LINK.finditer(line):
            yield n, m.group(1) or m.group(2)


def check(path: Path) -> list[str]:
    bad = []
    for n, target in links(path):
        if re.match(r"[a-z][a-z0-9+.-]*:", target, re.I):
            continue
        file_part, _, frag = target.partition("#")
        dest = path if not file_part else (path.parent / unquote(file_part))
        if not dest.exists():
            bad.append(f"{path.relative_to(ROOT)}:{n}: missing target {target}")
        elif frag and dest.suffix == ".md" and slug(unquote(frag)) not in anchors(dest):
            bad.append(f"{path.relative_to(ROOT)}:{n}: no heading for #{frag} in {dest.relative_to(ROOT)}")
    return bad


def main(argv):
    if argv:
        files = [Path(a).resolve() for a in argv]
    else:
        names = subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
        files = [ROOT / n for n in names if n]
    missing = [f for f in files if not f.exists()]
    if missing:
        print("ERROR: file not found: " + ", ".join(str(m) for m in missing))
        return 2
    problems, total = [], 0
    for f in files:
        total += sum(1 for _ in links(f))
        problems += check(f)
    for p in problems:
        print(p)
    print(f"{len(files)} files, {total} links, {len(problems)} broken")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
