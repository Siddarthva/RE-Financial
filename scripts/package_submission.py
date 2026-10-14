"""Build a submission zip from `git ls-files`, after a clean secret scan.

    python scripts/package_submission.py [--out dist/submission.zip]

Only files git tracks are included, so ignored files (environment files, tokens, caches, node_modules) cannot
end up in the zip. The scan runs first on a staged copy of exactly those files; any finding stops the build. Prints counts, never values.
"""
from __future__ import annotations
import argparse
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import scan_secrets  # noqa: E402


def tracked_files() -> list[str]:
    run = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True)
    names = [n for n in run.stdout.decode("utf-8").split("\0") if n]
    return [n for n in names if (ROOT / n).is_file()]  # skip entries deleted in the working tree


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="dist/submission.zip", help="zip path, relative to the repo root (default dist/submission.zip)")
    args = ap.parse_args(argv)

    out = (ROOT / args.out).resolve()
    if ROOT not in out.parents:
        print("Refusing to write the zip outside the repo.")
        return 2

    files = tracked_files()
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage"
        for name in files:  # scan exactly what would ship, not the whole working tree
            dest = stage / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, dest)
        if scan_secrets.main([str(stage)]) != 0:
            print("\nSecret scan is not clean; no zip was built.")
            return 1

    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True).stdout
    if dirty.strip():
        print("\nWarning: tracked files have uncommitted changes; the zip holds the working-tree versions.")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name in files:
            z.write(ROOT / name, name)
    print(f"\nWrote {out.relative_to(ROOT).as_posix()}: {len(files)} tracked files, {out.stat().st_size:,} bytes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
