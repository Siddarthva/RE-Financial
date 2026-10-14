"""qbo_test_connection.diagnose(): server failure text -> cause and next step; stored text is masked."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("qbo_test", ROOT / "01_connection" / "qbo_test_connection.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class DiagnoseTests(unittest.TestCase):
    def cause(self, text):
        return mod.diagnose(text)["cause"]

    def test_causes(self):
        cases = {
            "MCP error -32602: Input validation error: Invalid arguments for tool get_company_info: Required at params": "bad_request",
            "Error: QuickBooks authorization is invalid or expired and cannot be renewed": "expired_token",
            "Error: Failed to refresh Quickbooks token: invalid_grant": "expired_token",
            "Error: HTTP 401 Unauthorized": "expired_token",
            "Error: invalid_client": "bad_client",
            "Error: ApplicationAuthorizationFailed 403": "wrong_environment",
            "Error: fetch failed ECONNRESET": "network",
            "Error: 503 ServiceUnavailable": "rate_or_outage",
            "Error: something odd": "unknown",
        }
        for text, want in cases.items():
            self.assertEqual(self.cause(text), want, text)

    def test_every_diagnosis_names_a_next_step(self):
        for code, _, advice in mod.DIAGNOSES:
            self.assertTrue(advice.endswith("."), code)

    def test_stored_text_hides_ids_and_tokens(self):
        d = mod.diagnose("Error: realmId 9341455123456789 token AbCdEf0123456789AbCdEf0123456789xyz denied")
        self.assertNotIn("9341455123456789", d["server_said"])
        self.assertNotIn("AbCdEf0123456789", d["server_said"])


if __name__ == "__main__":
    unittest.main()
