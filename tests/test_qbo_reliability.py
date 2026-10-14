"""qbo_test_connection.test_connection() end to end against a fake stdio MCP server (needs Node).

Covers the reliability table in 01_connection/README.md: server missing, not built, Node missing,
no response (timeout), server exits, each QuickBooks failure text, bad JSON, and success.
No network, no credentials: the fake server is a few lines of JS written to a temp folder.
"""
import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("qbo_rel", ROOT / "01_connection" / "qbo_test_connection.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

FAKE = r"""
const rl = require('readline').createInterface({input: process.stdin});
const mode = process.env.FAKE_MODE || 'ok';
if (mode === 'exit') { process.stderr.write('Error: invalid_grant refresh failed\n'); process.exit(1); }
rl.on('line', (line) => {
  const m = JSON.parse(line);
  if (m.method === 'initialize') return console.log(JSON.stringify({jsonrpc:'2.0', id:m.id, result:{protocolVersion:'2024-11-05', capabilities:{}, serverInfo:{name:'fake',version:'1'}}}));
  if (m.method !== 'tools/call') return;
  if (mode === 'hang') return;
  const text = mode === 'ok' ? JSON.stringify({CompanyInfo:{CompanyName:'Fake Co'}}) : mode === 'garbage' ? 'not json' : 'Error: ' + process.env.FAKE_TEXT;
  console.log(JSON.stringify({jsonrpc:'2.0', id:m.id, result:{content:[{type:'text', text}]}}));
});
"""


@unittest.skipUnless(shutil.which("node"), "Node.js not installed")
class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        dist = Path(self.tmp.name) / "dist"
        dist.mkdir()
        (dist / "index.js").write_text(FAKE, encoding="utf-8")
        self.index = dist / "index.js"

    def run_mode(self, mode, text="", timeout=None):
        env = {"FAKE_MODE": mode, "FAKE_TEXT": text}
        with mock.patch.object(mod, "SERVER", self.index), mock.patch.dict(os.environ, env):
            if timeout:
                real = mod._rpc
                with mock.patch.object(mod, "_rpc", lambda *a, **k: real(*a, **{**k, "timeout": timeout})):
                    return mod.test_connection()
            return mod.test_connection()

    def test_success(self):
        r = self.run_mode("ok")
        self.assertTrue(r["ok"])
        self.assertEqual(r["company_name"], "Fake Co")

    def test_failure_texts_map_to_causes(self):
        cases = {
            "invalid_grant": "expired_token",           # expired token
            "ApplicationAuthorizationFailed 403": "wrong_environment",
            "fetch failed ECONNRESET": "network",        # network down
            "429 Too Many Requests throttled": "rate_or_outage",  # rate limit
            "503 ServiceUnavailable": "rate_or_outage",  # outage
            "Input validation error: Required at params": "bad_request",
            "invalid_client": "bad_client",
        }
        for text, cause in cases.items():
            r = self.run_mode("err", text)
            self.assertFalse(r["ok"], text)
            self.assertEqual(r["cause"], cause, text)
            self.assertTrue(r["message"].endswith("."), text)

    def test_server_exits_with_stderr_is_diagnosed(self):
        r = self.run_mode("exit")
        self.assertFalse(r["ok"])
        self.assertEqual(r.get("cause"), "expired_token")  # stderr is diagnosed, and fast

    def test_no_response_times_out_with_message(self):
        r = self.run_mode("hang", timeout=2)
        self.assertFalse(r["ok"])
        self.assertIn("No response", r["message"])

    def test_non_json_company_info_is_still_connected_without_name(self):
        r = self.run_mode("garbage")
        self.assertTrue(r["ok"])
        self.assertIsNone(r["company_name"])

    def test_server_folder_missing(self):
        with mock.patch.object(mod, "SERVER", Path(self.tmp.name) / "nope" / "dist" / "index.js"):
            r = mod.test_connection()
        self.assertEqual(r["cause"], "server_missing")
        self.assertIn("clone", r["message"].lower())

    def test_server_not_built(self):
        self.index.unlink()
        with mock.patch.object(mod, "SERVER", self.index):
            r = mod.test_connection()
        self.assertEqual(r["cause"], "server_missing")
        self.assertIn("npm run build", r["message"])

    def test_node_missing(self):
        with mock.patch.object(mod, "SERVER", self.index), mock.patch.object(mod.subprocess, "Popen", side_effect=OSError):
            r = mod.test_connection()
        self.assertFalse(r["ok"])
        self.assertIn("Node.js was not found", r["message"])

    def test_messages_never_contain_secrets(self):
        r = self.run_mode("err", "Error: invalid_grant token AbCdEf0123456789AbCdEf0123456789xyz realm 9341455123456789")
        self.assertNotIn("9341455123456789", str(r))
        self.assertNotIn("AbCdEf0123456789", str(r))


if __name__ == "__main__":
    unittest.main()
