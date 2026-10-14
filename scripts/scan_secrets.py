"""Scan folders for secrets, QuickBooks realm IDs and tokens. Prints file:line and the pattern name, never the value.

    python scripts/scan_secrets.py PATH [PATH ...]      exit 1 if anything is found

`.env`, token and credential files are only listed by name; their contents are never opened.
"""
from __future__ import annotations
import fnmatch
import re
import sys
from pathlib import Path

SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".tmp", ".pytest_cache"}
TEXT_SUFFIXES = {".py", ".md", ".json", ".yaml", ".yml", ".txt", ".ts", ".js", ".cjs", ".mjs", ".toml", ".cfg", ".ini", ".csv", ".html", ".xml", ".example", ".sh", ".ps1", ".env"}
SECRET_NAMES = (".env", ".env.*", "*token*", "*credential*", "*.pem", "*.key")
SAFE_NAME_SUFFIXES = (".example", ".sample", ".template")
PLACEHOLDER = re.compile(r"(?i)your[_-]|example|placeholder|redacted|<[^>]*>|xxx|\.\.\.|process\.env|\$\{|changeme|dummy|fake|test[_-]?(secret|token)|\bnone\b|\bnull\b")

PATTERNS = {
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}"),
    "intuit_token": re.compile(r"\b(?:AB11|RT1-|AB1|XX11)[A-Za-z0-9_-]{30,}"),
    "bearer_header": re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{20,}"),
    "realm_id": re.compile(r"(?i)realm[_ ]?id[\"']?\s*[:=]\s*[\"']?\d{9,}|/company/\d{9,}|realmId=\d{9,}"),
    "secret_assignment": re.compile(r"(?i)(client[_-]?secret|refresh[_-]?token|access[_-]?token|api[_-]?key|password|authorization[_-]?code)[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9_\-./+=]{16,})"),
    "auth_code_in_url": re.compile(r"[?&]code=[A-Za-z0-9_\-]{16,}"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "email_address": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
}
ALLOW_MARKER = "scan-secrets: allow-fake-fixtures"  # in the first 30 lines of a file of deliberately fake values
INFO_ONLY = {"email_address"}  # personal data, not a credential; reported separately


def is_secret_name(name: str) -> bool:
    low = name.lower()
    return not low.endswith(SAFE_NAME_SUFFIXES) and any(fnmatch.fnmatch(low, p) for p in SECRET_NAMES)


def scan_text(text: str):
    """Yield (line number, pattern name) for each hit; placeholders are ignored."""
    for n, line in enumerate(text.splitlines(), 1):
        for name, rx in PATTERNS.items():
            for m in rx.finditer(line):
                if name == "secret_assignment" and PLACEHOLDER.search(m.group(2)):
                    continue
                if name != "email_address" and PLACEHOLDER.search(m.group(0)) and name not in {"jwt", "intuit_token"}:
                    continue
                yield n, name
                break


def scan(paths):
    findings, secret_files, allowed, scanned = [], [], [], 0
    for root in map(Path, paths):
        for p in sorted(root.rglob("*")):
            if not p.is_file() or SKIP_DIRS & set(p.relative_to(root).parts[:-1]):
                continue
            if is_secret_name(p.name):
                secret_files.append(p)  # name only: never opened
                continue
            if p.suffix.lower() not in TEXT_SUFFIXES or p.stat().st_size > 5_000_000:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            scanned += 1
            if any(ALLOW_MARKER in line for line in text.splitlines()[:30]):
                allowed.append(p)  # deliberate fake fixtures (redaction tests); listed in the report
                continue
            findings += [(p, n, name) for n, name in scan_text(text)]
    return findings, secret_files, scanned, allowed


def main(argv=None):
    paths = argv if argv is not None else sys.argv[1:]
    if not paths:
        raise SystemExit(__doc__)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    findings, secret_files, scanned, allowed = scan(paths)
    serious = [f for f in findings if f[2] not in INFO_ONLY]
    info = [f for f in findings if f[2] in INFO_ONLY]
    print(f"Scanned {scanned} text files in {len(paths)} folder(s).")
    print(f"Secret-like findings: {len(serious)}")
    for p, n, name in serious:
        print(f"  {name}: {p}:{n}")
    print(f"Email addresses (personal data, informational): {len(info)}")
    for p, n, _ in info:
        print(f"  {p}:{n}")
    print(f"Skipped as declared fake fixtures: {len(allowed)}")
    for p in allowed:
        print(f"  {p}")
    print(f"Secret-named files present (names only, contents not opened): {len(secret_files)}")
    for p in secret_files:
        print(f"  {p}")
    return 1 if serious or secret_files else 0


if __name__ == "__main__":
    raise SystemExit(main())
