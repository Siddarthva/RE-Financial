import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("redact_and_verify", ROOT / "evidence" / "quickbooks" / "redact_and_verify.py")
rv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rv)

# Fake values only — shaped like real secrets so the patterns are exercised.  scan-secrets: allow-fake-fixtures
SAMPLE = {
    "realmId": "1234567890123456",
    "Header": {"Note": "see https://quickbooks.api.intuit.com/v3/company/1234567890123456/reports/ProfitAndLoss"},
    "links": ["https://user:p4ssw0rd@proxy.example.com:8080/", "https://example.com/callback?code=AB12cd34&realmId=123"],
    "auth": {"access_token": "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJmYWtlIn0.c2lnbmF0dXJl", "refresh_token": "AB11fake"},
    "header": "Authorization: Bearer abcdefghijklmnop123",
    "contact": "owner@example.com",
    "amount": "4875.00", "Id": "1", "account_id": "35",
}


class EvidenceRedactionTests(unittest.TestCase):
    def test_secrets_are_removed_and_amounts_kept(self):
        log = {}
        text = json.dumps(rv.redact(SAMPLE, log))
        for secret in ["1234567890123456", "p4ssw0rd", "AB12cd34", "eyJhbGci", "AB11fake",
                       "abcdefghijklmnop123", "owner@example.com"]:
            self.assertNotIn(secret, text)
        self.assertEqual(rv.residual(text), [])
        self.assertIn('"amount": "4875.00"', text)
        self.assertIn('"Id": "1"', text)

    def test_residual_scan_flags_unredacted_text(self):
        self.assertIn("url_with_credentials", rv.residual("https://u:pw@host/x"))
        self.assertIn("long_numeric_id", rv.residual("realm 1234567890123456"))

    def test_saved_evidence_has_no_secret_patterns(self):
        files = list((ROOT / "evidence" / "quickbooks").glob("*.response.redacted.*"))
        self.assertEqual(len(files), 8)
        for f in files:
            self.assertEqual(rv.residual(f.read_text(encoding="utf-8")), [], f.name)


if __name__ == "__main__":
    unittest.main()
