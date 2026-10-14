"""scripts/scan_secrets.py finds planted fake secrets, ignores placeholders, never opens secret-named files.  scan-secrets: allow-fake-fixtures (planted fake values)"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("scan_secrets", ROOT / "scripts" / "scan_secrets.py")
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)


class ScanTests(unittest.TestCase):
    def run_scan(self, files):
        with tempfile.TemporaryDirectory() as d:
            for name, text in files.items():
                (Path(d) / name).write_text(text, encoding="utf-8")
            return scan.scan([d])

    def test_finds_planted_values_by_kind(self):
        findings, _, _, _ = self.run_scan({"a.json": '{"realmId": "1234567890123456"}\n{"access_token": "' + "k9Zt" * 8 + '"}\nAuthorization: Bearer ' + "a" * 25})
        self.assertEqual(sorted(k for _, _, k in findings), ["bearer_header", "realm_id", "secret_assignment"])

    def test_placeholders_and_env_references_are_ignored(self):
        findings, _, _, _ = self.run_scan({"a.md": "QUICKBOOKS_CLIENT_SECRET=your_client_secret_here\nclient_secret = process.env.QUICKBOOKS_CLIENT_SECRET\n"})
        self.assertEqual(findings, [])

    def test_secret_named_files_are_listed_but_not_opened(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".env").write_text("client_secret=" + "z" * 30, encoding="utf-8")
            (Path(d) / "oauth_token.json").write_text("{}", encoding="utf-8")
            (Path(d) / ".env.example").write_text("client_secret=your_value", encoding="utf-8")
            findings, files, _, _ = scan.scan([d])
        self.assertEqual(findings, [])
        self.assertEqual(sorted(p.name for p in files), [".env", "oauth_token.json"])

    def test_file_paths_are_scanned_and_missing_paths_fail(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "a.json"
            f.write_text('{"realmId": "1234567890123456"}', encoding="utf-8")
            findings, _, scanned, _ = scan.scan([str(f)])
            self.assertEqual((scanned, [k for _, _, k in findings]), (1, ["realm_id"]))
            with self.assertRaises(SystemExit):
                scan.scan([str(Path(d) / "missing.json")])

    def test_values_are_never_in_the_report_output(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.txt").write_text("refresh_token=" + "Q" * 40, encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = scan.main([d])
        self.assertEqual(code, 1)
        self.assertNotIn("Q" * 20, buf.getvalue())


if __name__ == "__main__":
    unittest.main()
