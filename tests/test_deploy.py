"""Hosting (partial by design): the Dockerfile/compose run one client per container offline, and the MCP launcher starts
one server process per client with its own paths. Docker is not installed on the build machine, so the container is
checked by structure and by running the pipeline in a copy of exactly the files the image and mounts would contain."""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import mcp_per_client as mpc  # noqa: E402

COMPOSE = ROOT / "deploy" / "compose.yaml"
DOCKERFILE = ROOT / "Dockerfile"


class ComposeAndDockerfileTests(unittest.TestCase):
    def setUp(self):
        self.engine = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]["engine"]

    def test_engine_has_no_network_and_read_only_root(self):
        self.assertEqual(self.engine["network_mode"], "none")
        self.assertIs(self.engine["read_only"], True)
        self.assertNotIn("ports", self.engine)
        self.assertEqual(self.engine["cap_drop"], ["ALL"])
        self.assertNotEqual(str(self.engine["user"]).split(":")[0], "0")

    def test_only_outputs_of_the_client_is_writable(self):
        vols = self.engine["volumes"]
        writable = [v for v in vols if not v.get("read_only")]
        self.assertEqual([v["target"] for v in writable], ["/app/outputs/${CLIENT:?set CLIENT}"])
        self.assertEqual(writable[0]["source"], "../outputs/${CLIENT:?set CLIENT}")
        client = next(v for v in vols if v["target"].startswith("/app/clients/"))
        self.assertTrue(client["read_only"])
        self.assertEqual(client["source"], "../clients/${CLIENT:?set CLIENT}")  # one client folder, never clients/

    def test_image_holds_code_only(self):
        copies = re.findall(r"^COPY\s+(\S+)\s+(\S+)", DOCKERFILE.read_text(encoding="utf-8"), re.M)
        sources = [s for s, _ in copies]
        for forbidden in ("clients", "data", "outputs", ".secrets", ".env", "quickbooks-online-mcp-server", "."):
            self.assertFalse(any(s.rstrip("/") == forbidden or s.startswith(forbidden + "/") for s in sources), forbidden)
        text = DOCKERFILE.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^USER 10001$")
        self.assertNotIn("QUICKBOOKS", text)


def _simulated_container(app: Path, client: str, data: Path | None):
    """Lay out /app as the image + compose mounts would: the Dockerfile's COPY sources plus one client's folder and data."""
    for src, dst in re.findall(r"^COPY\s+(\S+)\s+(\S+)", DOCKERFILE.read_text(encoding="utf-8"), re.M):
        target = app / dst.removeprefix("/app/")
        if (ROOT / src).is_dir():
            shutil.copytree(ROOT / src, target, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / src, target)
    shutil.copytree(ROOT / "clients" / client, app / "clients" / client)
    if data:
        shutil.copytree(data, app / "data")
    (app / "outputs" / client).mkdir(parents=True)


class SimulatedContainerRunTests(unittest.TestCase):
    """Same numbers inside the container layout as in the local run (abc 2026-06)."""

    def test_abc_packet_identical_to_local_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            app = tmp / "app"
            _simulated_container(app, "abc", ROOT / "data")
            self.assertEqual(sorted(p.name for p in (app / "clients").iterdir()), ["abc"])
            env = {k: v for k, v in os.environ.items() if not k.upper().startswith("QUICKBOOKS_")}
            r = subprocess.run([sys.executable, "-X", "utf8", "scripts/run_pipeline.py", "abc", "2026-06"], cwd=app, env=env,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            local = tmp / "local_outputs"
            r2 = subprocess.run([sys.executable, "-X", "utf8", "scripts/run_pipeline.py", "abc", "2026-06", "--outputs-root", str(local)],
                                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
            inside = json.loads((app / "outputs" / "abc" / "review_packet_2026-06.json").read_text(encoding="utf-8"))
            outside = json.loads((local / "abc" / "review_packet_2026-06.json").read_text(encoding="utf-8"))
            self.assertEqual(inside, outside)
            written = {p.relative_to(app).parts[:2] for p in app.rglob("*") if p.is_file() and p.stat().st_mtime > 0
                       and p.relative_to(app).parts[0] == "outputs"}
            self.assertEqual(written, {("outputs", "abc")})


FAKE_SERVER = textwrap.dedent("""
    import json, os, sys
    line = sys.stdin.readline()
    req = json.loads(line)
    keys = ("QUICKBOOKS_TOKEN_STORE_PATH", "QUICKBOOKS_DISABLE_WRITE", "QUICKBOOKS_DISABLE_UPDATE", "QUICKBOOKS_DISABLE_DELETE",
            "QUICKBOOKS_REFRESH_TOKEN", "MCP_CLIENT_ID")
    info = {"cwd": os.getcwd(), "pid": os.getpid(), "env": {k: os.environ.get(k) for k in keys}}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": {"serverInfo": info}}) + "\\n")
    sys.stdout.flush()
    sys.stdin.readline()
""")


class McpPerClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.server = t / "fake_server.py"
        self.server.write_text(FAKE_SERVER, encoding="utf-8")
        self.secrets, self.runtime = t / "secrets", t / "runtime"
        for c in ("abc", "xyz"):
            (self.secrets / c).mkdir(parents=True)
            (self.secrets / c / "qbo.env").write_text("SENTINEL_DO_NOT_READ=1\n", encoding="utf-8")
        self.saved = {k: os.environ.get(k) for k in ("QUICKBOOKS_REFRESH_TOKEN", "QUICKBOOKS_DISABLE_WRITE")}
        os.environ["QUICKBOOKS_REFRESH_TOKEN"] = "parent-value-must-not-leak"
        os.environ["QUICKBOOKS_DISABLE_WRITE"] = "false"

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def test_two_clients_get_separate_processes_and_paths_and_env_file_is_never_opened(self):
        opened = []
        watch = {os.path.normcase(str(self.secrets / c / "qbo.env")) for c in ("abc", "xyz")}

        def hook(event, args):
            if event == "open" and isinstance(args[0], (str, os.PathLike)) and os.path.normcase(os.fspath(args[0])) in watch:
                opened.append(args[0])
        sys.addaudithook(hook)
        infos, procs = {}, []
        try:
            for c in ("abc", "xyz"):
                p = mpc.plan(c, self.secrets, self.runtime)
                proc = mpc.start(p, [sys.executable, str(self.server)])
                procs.append(proc)
                infos[c] = mpc.handshake(proc, timeout=20)["result"]["serverInfo"]
        finally:
            for proc in procs:
                proc.kill()
                proc.wait()
        self.assertEqual(opened, [])
        a, x = infos["abc"], infos["xyz"]
        self.assertNotEqual(a["pid"], x["pid"])
        self.assertEqual(Path(a["cwd"]).resolve(), (self.runtime / "abc").resolve())
        self.assertEqual(Path(x["cwd"]).resolve(), (self.runtime / "xyz").resolve())
        self.assertEqual(a["env"]["QUICKBOOKS_TOKEN_STORE_PATH"], str(self.secrets / "abc" / "qbo.env"))
        self.assertEqual(x["env"]["QUICKBOOKS_TOKEN_STORE_PATH"], str(self.secrets / "xyz" / "qbo.env"))
        for info in (a, x):
            self.assertIsNone(info["env"]["QUICKBOOKS_REFRESH_TOKEN"])  # parent credentials are not inherited
            for f in mpc.FLAGS:
                self.assertEqual(info["env"][f], "true")  # forced, even though the parent says false
        self.assertEqual((a["env"]["MCP_CLIENT_ID"], x["env"]["MCP_CLIENT_ID"]), ("abc", "xyz"))

    def test_check_mode_prints_one_row_per_client(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = mpc.main(["--clients", "abc", "xyz", "--secrets-root", str(self.secrets), "--runtime-root", str(self.runtime),
                           "--check", "--server", sys.executable, str(self.server)])
        self.assertEqual(rc, 0, out.getvalue())
        rows = [l for l in out.getvalue().splitlines() if l.startswith("| abc") or l.startswith("| xyz")]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r.rstrip().endswith("| ok |") for r in rows), rows)

    def test_bad_client_id_refused_before_any_path_is_built(self):
        with self.assertRaises(ValueError):
            mpc.plan("../abc", self.secrets, self.runtime)


if __name__ == "__main__":
    unittest.main()
