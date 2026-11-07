"""Sudoku central bounded stage contracts: no SSH or DB writes in tests."""
from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from app.standalone_subscription_accounts import StandaloneAccountSecret
from scripts import twinpanel_central_sudoku_node_bulk_v1 as stage


class SudokuStageTests(unittest.TestCase):
    def secret(self):
        return StandaloneAccountSecret(
            protocol="sudoku",subscription_id=17,username="tp-sub-17",
            sudoku_client_key="a"*64,sudoku_master_public_key="b"*64,
            sudoku_master_private_key="c"*64,sudoku_port=30016,
        )

    def test_client_contract_and_uri(self):
        node=SimpleNamespace(id=14,name="Hidden Node",public_ip="203.0.113.12",public_domain="")
        item=stage.client_item(node,self.secret())
        cfg=json.loads(item["config"])
        self.assertEqual(cfg["local_port"],1080)
        self.assertEqual(cfg["server_address"],"203.0.113.12:30016")
        self.assertEqual(cfg["key"],"a"*64)
        self.assertTrue(item["uri"].startswith("sudoku://"))
        self.assertEqual(item["telemetry_identity"],"sudoku-sub-17:30016")

    def test_apply_confirmation_and_capacity(self):
        with self.assertRaises(SystemExit):
            stage.args(["--node-id","14","--apply"])
        self.assertEqual(stage.args(["--node-id","14","--limit","1900"]).limit,1900)
        parsed=stage.args(["--node-id","14","--limit","3000","--apply",
                           "--confirm-node-id","14"])
        self.assertEqual(parsed.limit,3000)

    def test_identity_required(self):
        node=SimpleNamespace(id=14,name="Hidden",public_ip="203.0.113.12",public_domain="")
        with self.assertRaisesRegex(RuntimeError,"IDENTITY_INCOMPLETE"):
            stage.client_item(node,StandaloneAccountSecret(
                protocol="sudoku",subscription_id=17,username="tp-sub-17"))


if __name__=="__main__":
    unittest.main()
