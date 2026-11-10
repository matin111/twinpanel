"""No guessed Sudoku traffic: kernel-owned per-user counters or no billing."""
from __future__ import annotations
import ast
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"app/services/sudoku_legacy_systemd_accounting_v1.py"
WORKER=ROOT/"scripts/twinpanel_sudoku_fast_presence_worker.py"
LEGACY=ROOT/"app/services/modern_quota_runtime_v257.py"
SHARED=ROOT/"app/services/sudoku_shared_native_presence_v1.py"


def pure_helpers():
    source=SOURCE.read_text()
    tree=ast.parse(source)
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and
           n.name in ("eligible_legacy_units","validate_counters")]
    env={"Any":object,"MAX_UNITS":3000,"re":re,
         "canonical":type("Canonical",(),{
           "_sudoku_port":staticmethod(lambda text:int(text.rsplit(":",1)[1]) if ":" in text else None)
         })()}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),"test","exec"),env)
    return env


class SudokuMetering(unittest.TestCase):
    def test_sources_and_remote_script_compile(self):
        for path in (SOURCE,WORKER,LEGACY,SHARED):
            ast.parse(path.read_text())
        tree=ast.parse(SOURCE.read_text())
        remote=next(n.value.value for n in tree.body if isinstance(n,ast.Assign)
                    for target in n.targets if isinstance(target,ast.Name) and target.id=="_REMOTE")
        compile(remote,"node_readonly_sudoku_systemd_meter.py","exec")
        self.assertIn("systemctl\",\"set-property\",\"--runtime\"",remote)
        self.assertIn('before.get("MainPID")',remote)
        self.assertIn('after.get("MainPID")!=before.get("MainPID")',remote)
        self.assertIn('IPIngressBytes',remote)
        self.assertNotIn('systemctl\",\"restart',remote)
        self.assertNotIn('iptables',remote)
        self.assertNotIn('secret=',remote)
        self.assertIn("cfg.get(\"mode\")!=\"server\"",remote)

    def test_eligible_ports_are_exact_and_deduplicated(self):
        env=pure_helpers();items=[
            {"subscription_id":12,"telemetry_identity":"sudoku-sub-12:18000"},
            {"subscription_id":12,"telemetry_identity":"sudoku-sub-12:18000"},
            {"subscription_id":22,"telemetry_identity":"missing"},
        ]
        self.assertEqual(env["eligible_legacy_units"](items),[{"sid":12,"port":18000}])

    def test_reject_spoofed_or_replayed_metrics(self):
        parse=pure_helpers()["validate_counters"]
        units=[{"sid":12,"port":18000}]
        good={"marker":"TP_SUDOKU_LEGACY_IPACCOUNTING_V1",
              "counters":[{"sid":12,"port":18000,"epoch":"a"*32+":"+"b"*32,"ingress":901}]}
        self.assertEqual(parse(good,units)[12]["ingress"],901)
        bad=[
            {**good,"marker":"fake"},
            {**good,"counters":good["counters"]*2},
            {**good,"counters":[{**good["counters"][0],"sid":13}]},
            {**good,"counters":[{**good["counters"][0],"port":18001}]},
            {**good,"counters":[{**good["counters"][0],"epoch":"nope"}]},
            {**good,"counters":[{**good["counters"][0],"ingress":-1}]},
            {**good,"counters":[{**good["counters"][0],"ingress":True}]},
        ]
        for item in bad:
            with self.assertRaises(ValueError):
                parse(item,units)

    def test_reuse_canonical_quota_ledger_not_synthetic_sessions(self):
        source=SOURCE.read_text()
        self.assertIn("canonical._baseline_or_apply_cumulative(",source)
        self.assertIn("source_key=f\"sudoku:legacy:{sid}:{counter['epoch']}\"",source)
        self.assertIn("uplink=int(counter[\"ingress\"]),downlink=0",source)
        self.assertNotIn("sqlite",source)
        self.assertNotIn("bytes_per_second",source)
        self.assertNotIn("estimated_bytes",source)
        self.assertNotIn("open_session(",source)
        worker=WORKER.read_text()
        self.assertIn("collect_legacy_unit_counters(conn, devices)",worker)
        self.assertIn("apply_legacy_unit_counters(",worker)
        self.assertIn("if central_shared:",worker)
        self.assertIn("collect_shared_native_users(conn)",worker)
        self.assertIn("canonical._collect_established_tcp_ports(conn)",worker)
        self.assertIn("db.commit()",worker)

    def test_bad_account_does_not_starve_others(self):
        for path in (LEGACY,SHARED):
            source=path.read_text()
            self.assertIn("subscription_not_active",source)
            self.assertIn("except HTTPException as exc:",source)
            self.assertIn("continue",source)
        # Shared daemon still must NEVER bill based on connection count.
        self.assertIn('"usage_supported": False',SHARED.read_text())


if __name__=="__main__":
    unittest.main()
