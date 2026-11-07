"""Central Mieru stage tests, no DB or SSH access."""
from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from app.standalone_subscription_accounts import StandaloneAccountSecret
from scripts import twinpanel_central_mieru_node_bulk_v1 as stage


class MieruStageTests(unittest.TestCase):
    def test_client_schema_matches_existing_mieru_runtime(self):
        node = SimpleNamespace(id=14, name="Test Exit",
                               public_ip="203.0.113.12", public_domain="")
        identity = StandaloneAccountSecret(
            protocol="mieru", subscription_id=17,
            username="tp-sub-17", password="test-secret-value")
        item = stage.client_item(node, identity, 12345)
        doc = json.loads(item["config"])
        self.assertEqual(doc["activeProfile"], "tp-sub-17")
        self.assertEqual(doc["profiles"][0]["user"]["password"],
                         "test-secret-value")
        self.assertEqual(doc["profiles"][0]["servers"][0]["portBindings"],
                         [{"port": 12345, "protocol":"TCP"},
                          {"port": 12345, "protocol":"UDP"}])

    def test_empty_server_address_fails(self):
        node = SimpleNamespace(id=14, name="Hidden", public_ip="", public_domain="")
        secret = StandaloneAccountSecret(
            protocol="mieru", subscription_id=17,
            username="tp-sub-17", password="test-secret-value")
        with self.assertRaisesRegex(RuntimeError, "IDENTITY_INVALID"):
            stage.client_item(node, secret, 12345)

    def test_apply_must_be_explicit(self):
        with self.assertRaises(SystemExit):
            stage.args(["--node-id","14","--apply"])
        self.assertTrue(stage.args(["--node-id","14","--apply",
                                    "--confirm-node-id","14"]).apply)


if __name__ == "__main__":
    unittest.main()
