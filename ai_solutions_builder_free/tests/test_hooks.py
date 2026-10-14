"""The secret-file guard blocks what CLAUDE.md forbids; the post-edit hook ignores non-src edits.

The post-edit hook's real test run is not exercised here: it runs this suite, so it would recurse.
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / ".claude" / "hooks"


def run_hook(script, tool, **tool_input):
    event = {"tool_name": tool, "tool_input": tool_input}
    return subprocess.run([sys.executable, str(HOOKS / script)], input=json.dumps(event), capture_output=True, text=True)


class GuardSecretsTests(unittest.TestCase):
    def test_read_of_secret_files_is_blocked(self):
        for path in [".env", r"C:\RE\quickbooks-online-mcp-server\.env", "x/.env.local", "a/oauth_tokens.json",
                     "Token.txt", "gcp-credentials.json", "credential"]:
            with self.subTest(path=path):
                r = run_hook("guard_secrets.py", "Read", file_path=path)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn("secret file", r.stderr)

    def test_bash_commands_naming_secret_files_are_blocked(self):
        for cmd in ["cat .env", r"type ..\quickbooks-online-mcp-server\.env", "head -n1 \"a/refresh_token.json\"",
                    "python -c \"print(open('.env').read())\"", "Get-Content creds/credentials.json", "grep KEY a/.env.production"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(run_hook("guard_secrets.py", "Bash", command=cmd).returncode, 2)

    def test_ordinary_calls_are_allowed(self):
        for tool, args in [("Read", {"file_path": "src/abc_workbook_adapter.py"}), ("Read", {"file_path": ".env.example"}),
                           ("Bash", {"command": "python -m pytest -q tests"}), ("Bash", {"command": "grep -rn token src"}),
                           ("Bash", {"command": "npm audit --json"}), ("Read", {"file_path": "README.md"})]:
            with self.subTest(tool=tool, args=args):
                self.assertEqual(run_hook("guard_secrets.py", tool, **args).returncode, 0)

    def test_post_edit_hook_ignores_files_outside_src(self):
        for path in ["README.md", "tests/test_hooks.py", "evals/GRADING.md", "src/notes.txt"]:
            with self.subTest(path=path):
                r = run_hook("test_after_edit.py", "Edit", file_path=str(HOOKS.parents[1] / path))
                self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))


if __name__ == "__main__":
    unittest.main()
