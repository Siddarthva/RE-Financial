"""Per-client file isolation for analysis runs.

While a ClientSandbox is active, every file open / mkdir / rename / remove in this process is checked
(via a Python audit hook, so it also covers pandas and openpyxl):

- reads under clients/ are allowed only inside clients/<client>/;
- reads under outputs/ are allowed only inside outputs/<client>/;
- writes are allowed only inside outputs/<client>/ (including the run's private temp dir, outputs/<client>/.tmp).

Anything else raises PermissionError. Paths outside clients/ and outputs/ (Python, installed libraries,
a shared source workbook declared in the client's config) stay readable.
"""
from __future__ import annotations
import os
import re
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

_active: "ClientSandbox | None" = None
_CLIENT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")  # same rule as run_client.CLIENT_ID
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
_MUTATING_EVENTS = {"os.mkdir", "os.rename", "os.replace", "os.remove", "os.rmdir", "shutil.rmtree", "shutil.copyfile"}


def _norm(path) -> str:
    # realpath expands Windows 8.3 short names (SIDDAR~1) and symlinks, so two spellings of one folder
    # compare equal. It only stats/readlinks, which this hook does not intercept, so it cannot recurse.
    path = os.fspath(path)
    if isinstance(path, bytes):
        path = os.fsdecode(path)
    try:
        return os.path.normcase(os.path.realpath(path))
    except (OSError, ValueError):
        return os.path.normcase(os.path.abspath(path))


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root + os.sep)


class ClientSandbox:
    def __init__(self, client: str, clients_root, outputs_root):
        self.client = client
        self.clients_root = _norm(clients_root)
        self.outputs_root = _norm(outputs_root)
        self.own_client_dir = _norm(Path(clients_root) / client)
        self.own_output_dir = _norm(Path(outputs_root) / client)
        self.accessed: list[tuple[str, str]] = []  # (mode, path) for audit/tests

    def check(self, path, write: bool):
        p = _norm(path)
        self.accessed.append(("write" if write else "read", p))
        if write:
            if not _inside(p, self.own_output_dir):
                raise PermissionError(f"[{self.client}] write outside outputs/{self.client}/ blocked: {path}")
            return
        if _inside(p, self.clients_root) and not _inside(p, self.own_client_dir) and p != self.clients_root:
            raise PermissionError(f"[{self.client}] read of another client's folder blocked: {path}")
        if _inside(p, self.outputs_root) and not _inside(p, self.own_output_dir) and p != self.outputs_root:
            raise PermissionError(f"[{self.client}] read of another client's outputs blocked: {path}")


def _audit(event, args):
    box = _active
    if box is None:
        return
    if event == "open":
        path, mode, flags = args
        if path is None or isinstance(path, int):
            return
        write = any(c in mode for c in "wax+") if isinstance(mode, str) else bool((flags or 0) & _WRITE_FLAGS)
        box.check(path, write)
    elif event in _MUTATING_EVENTS:
        for path in args[:2] if event in {"os.rename", "os.replace", "shutil.copyfile"} else args[:1]:
            if isinstance(path, (str, bytes, os.PathLike)):
                box.check(path, write=True)


sys.addaudithook(_audit)


@contextmanager
def client_sandbox(client: str, clients_root, outputs_root):
    """Activate isolation for one client; yields the ClientSandbox (its .accessed log is useful in tests)."""
    global _active
    if not _CLIENT_ID.match(str(client)):  # before any path is built: '../x' would escape outputs/
        raise ValueError(f"Invalid client id {client!r}; use lowercase letters, digits, '-' or '_' (e.g. abc).")
    if _active is not None:
        raise RuntimeError(f"A sandbox for client '{_active.client}' is already active.")
    box = ClientSandbox(client, clients_root, outputs_root)
    # Libraries (e.g. openpyxl) stage files in the temp dir; give this run a private one inside its own outputs.
    private_tmp = Path(outputs_root) / client / ".tmp"
    private_tmp.mkdir(parents=True, exist_ok=True)  # before activation: a fresh checkout has no outputs/ yet
    saved_tempdir = tempfile.tempdir
    _active = box
    try:
        tempfile.tempdir = str(private_tmp)
        yield box
    finally:
        tempfile.tempdir = saved_tempdir
        shutil.rmtree(private_tmp, ignore_errors=True)
        _active = None
