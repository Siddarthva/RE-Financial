"""Ten-plus-client isolation (clients/batch.yaml: abc, xyz, lmn, qbo_sandbox, c04-c10).

- Every ordered pair (a, b): a config for `a` tampered to read b's source data, or b's outputs, is refused (PermissionError).
- A batch run writes only inside each client's own outputs root.
- One client's failure does not stop or change the others.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import run_batch  # noqa: E402
import run_client  # noqa: E402
import sources  # noqa: E402
from client_sandbox import client_sandbox  # noqa: E402

CLIENTS = list(yaml.safe_load((ROOT / "clients" / "batch.yaml").read_text(encoding="utf-8")))


def source_files(cfg):
    return [Path(cfg["workbook_path"])] + ([Path(cfg["balance_sheet_path"])] if cfg.get("balance_sheet_path") else [])


class PairwiseRefusalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        cls.clients, cls.outputs = t / "clients", t / "outputs"
        cls.sources = {}
        owners = {}
        for c in CLIENTS:
            real = run_client.load_config(c)
            shutil.copytree(ROOT / "clients" / c, cls.clients / c)
            raw = yaml.safe_load((cls.clients / c / "config.yaml").read_text(encoding="utf-8"))
            if not real["workbook_path"].is_relative_to(ROOT / "clients" / c):  # data kept outside clients/<id>/
                raw["workbook"] = str(real["workbook_path"])
                if real.get("balance_sheet_path"):
                    raw["balance_sheet_file"] = str(real["balance_sheet_path"])
                owners[str(real["workbook_path"].parent)] = c
            (cls.clients / c / "config.yaml").write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
            cls.sources[c] = source_files(run_client.load_config(c, cls.clients))
            (cls.outputs / c).mkdir(parents=True)
            (cls.outputs / c / "review_packet_2026-06.json").write_text("{}", encoding="utf-8")
        (cls.clients / "data_owners.yaml").write_text(yaml.safe_dump(owners), encoding="utf-8")
        cls.real_cfg = {c: yaml.safe_load((cls.clients / c / "config.yaml").read_text(encoding="utf-8")) for c in CLIENTS}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def tamper(self, a, path):
        raw = dict(self.real_cfg[a], workbook=str(path))
        if raw.get("balance_sheet_file"):
            raw["balance_sheet_file"] = str(path)
        (self.clients / a / "config.yaml").write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")

    def restore(self, a):
        (self.clients / a / "config.yaml").write_text(yaml.safe_dump(self.real_cfg[a], sort_keys=False, allow_unicode=True), encoding="utf-8")

    def attempt(self, a):
        with client_sandbox(a, self.clients, self.outputs):
            cfg = run_client.load_config(a, self.clients)
            sources.income_statement(cfg)

    def test_own_data_is_readable(self):
        for a in CLIENTS:
            with self.subTest(client=a):
                self.attempt(a)

    def test_every_pair_refused_for_other_clients_data_and_outputs(self):
        pairs = 0
        for a in CLIENTS:
            for b in CLIENTS:
                if a == b:
                    continue
                for target in (self.sources[b][0], self.outputs / b / "review_packet_2026-06.json"):
                    with self.subTest(client=a, other=b, target=target.name):
                        self.tamper(a, target)
                        try:
                            with self.assertRaises(PermissionError):
                                self.attempt(a)
                        finally:
                            self.restore(a)
                pairs += 1
        self.assertEqual(pairs, len(CLIENTS) * (len(CLIENTS) - 1))
        self.assertGreaterEqual(len(CLIENTS), 10)


class BatchIsolationTests(unittest.TestCase):
    def test_batch_writes_only_inside_each_clients_own_root_and_a_failure_is_contained(self):
        picks = ["c04", "c05", "c06", "c09"]
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            clients = t / "clients"
            for c in picks:
                shutil.copytree(ROOT / "clients" / c, clients / c)
            (clients / "c05" / "c05_financials.xlsx").write_bytes(b"not a workbook")  # c05 breaks
            batch = t / "batch.yaml"
            batch.write_text(yaml.safe_dump({c: {"month": {"c04": "2026-06", "c05": "2026-07", "c06": "2026-08", "c09": "2026-05"}[c],
                                                 "expect": "success"} for c in picks}), encoding="utf-8")
            rc = run_batch.main(["--root", str(t / "run"), "--clients-root", str(clients), "--batch", str(batch), "--jobs", "4"])
            rows = {r["client"]: r for r in json.loads((t / "run" / "batch_results.json").read_text(encoding="utf-8"))["rows"]}
            self.assertEqual(rc, 1)  # c05 did not behave as declared
            self.assertEqual(rows["c05"]["status"], "refused")
            for c in ("c04", "c06", "c09"):
                self.assertEqual(rows[c]["status"], "success", rows[c])
            # Every file is under <root>/<client>/; nothing else was written.
            for p in (t / "run").rglob("*"):
                if p.is_file() and p.name != "batch_results.json":
                    rel = p.relative_to(t / "run").parts
                    self.assertIn(rel[0], picks, p)
                    if rel[1] != ".proc_tmp":
                        self.assertEqual(rel[1], rel[0], p)  # <root>/<id>/<id>/...
            # c04's packet with c05 failing alongside equals c04 run alone.
            solo = t / "solo"
            batch.write_text(yaml.safe_dump({"c04": {"month": "2026-06", "expect": "success"}}), encoding="utf-8")
            self.assertEqual(run_batch.main(["--root", str(solo), "--clients-root", str(clients), "--batch", str(batch), "--jobs", "1"]), 0)
            read = lambda r: json.loads((r / "c04" / "c04" / "review_packet_2026-06.json").read_text(encoding="utf-8"))
            self.assertEqual(read(t / "run"), read(solo))


if __name__ == "__main__":
    unittest.main()
