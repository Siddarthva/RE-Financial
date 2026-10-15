import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from client_sandbox import client_sandbox
from run_client import CLIENTS_ROOT, run


def norm(p):
    return os.path.normcase(os.path.realpath(p))


class LmnIsolationTests(unittest.TestCase):
    """lmn cannot read or write abc/xyz folders or outputs, and abc cannot touch lmn."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.outputs = Path(self.tmp.name) / "outputs"
        for c in ("abc", "xyz"):
            (self.outputs / c).mkdir(parents=True)
            (self.outputs / c / "private.txt").write_text(c + " only", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _spy_run(self, client):
        import client_sandbox as sb
        seen = []
        original = sb.ClientSandbox.check
        def spy(self_, path, write):
            seen.append((write, norm(path)))
            return original(self_, path, write)
        sb.ClientSandbox.check = spy
        try:
            run(client, CLIENTS_ROOT, self.outputs)
        finally:
            sb.ClientSandbox.check = original
        self.assertTrue(seen, "sandbox saw no file access")
        return seen

    def test_lmn_run_touches_nothing_of_abc_or_xyz(self):
        seen = self._spy_run("lmn")
        forbidden = [norm(CLIENTS_ROOT / c) for c in ("abc", "xyz")] + [norm(self.outputs / c) for c in ("abc", "xyz")]
        self.assertFalse([p for _, p in seen if any(p.startswith(f) for f in forbidden)])
        writes = [p for w, p in seen if w]
        self.assertTrue(writes and all(p.startswith(norm(self.outputs / "lmn")) for p in writes), writes)

    def test_abc_run_touches_nothing_of_lmn(self):
        seen = self._spy_run("abc")
        forbidden = [norm(CLIENTS_ROOT / "lmn"), norm(self.outputs / "lmn")]
        self.assertFalse([p for _, p in seen if any(p.startswith(f) for f in forbidden)])
        self.assertFalse((self.outputs / "lmn").exists())

    def test_lmn_run_leaves_other_outputs_unchanged(self):
        run("lmn", CLIENTS_ROOT, self.outputs)
        files = sorted(str(p.relative_to(self.outputs)).replace(os.sep, "/") for p in self.outputs.rglob("*") if p.is_file())
        self.assertEqual(files, ["abc/private.txt", "lmn/analysis.xlsx", "lmn/commentary.md",
                                 "lmn/summary.json", "xyz/private.txt"])
        self.assertEqual((self.outputs / "abc" / "private.txt").read_text(encoding="utf-8"), "abc only")

    def test_lmn_sandbox_blocks_other_clients_both_ways(self):
        with client_sandbox("lmn", CLIENTS_ROOT, self.outputs):
            with self.assertRaises(PermissionError):
                (CLIENTS_ROOT / "xyz" / "config.yaml").read_text(encoding="utf-8")
            with self.assertRaises(PermissionError):
                (self.outputs / "abc" / "private.txt").read_text(encoding="utf-8")
            with self.assertRaises(PermissionError):
                open(self.outputs / "xyz" / "leak.txt", "w").close()
            (CLIENTS_ROOT / "lmn" / "config.yaml").read_text(encoding="utf-8")
        with client_sandbox("abc", CLIENTS_ROOT, self.outputs):
            with self.assertRaises(PermissionError):
                (CLIENTS_ROOT / "lmn" / "lmn_financials.xlsx").read_bytes()
            with self.assertRaises(PermissionError):
                open(self.outputs / "lmn" / "x.txt", "w").close()


if __name__ == "__main__":
    unittest.main()
