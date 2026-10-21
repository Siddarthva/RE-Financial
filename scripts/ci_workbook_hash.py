"""Exit 1 unless the source workbook's SHA-256 is the recorded one. Used by CI before and after the checks.

    python scripts/ci_workbook_hash.py
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "data" / "ABC Inc - Financial Statements.xlsx"
WORKBOOK_SHA = "75da8d679a89551f9e46b3563b7cfc724d9aaeabe0444b0214d455a0b335a0ea"  # same constant as regress.py

if __name__ == "__main__":
    got = hashlib.sha256(WORKBOOK.read_bytes()).hexdigest()
    print(f"sha256 {got[:16]}… {'matches' if got == WORKBOOK_SHA else 'DIFFERS from ' + WORKBOOK_SHA[:16] + '…'}")
    sys.exit(0 if got == WORKBOOK_SHA else 1)
