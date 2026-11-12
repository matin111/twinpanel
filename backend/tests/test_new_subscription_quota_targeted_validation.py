"""New subscription quota validation uses the canonical quota agent mapping.

No production node, subscription, credentials or filesystem side effects.
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Node, NodeType, ProtocolCredential, SubscriptionNode
from app.services import quota_refresh


class NewSubscriptionQuotaMappingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        for model in (Node, ProtocolCredential, SubscriptionNode):
            model.__table__.create(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def node(self, nid: int, kind: NodeType = NodeType.EXIT,
             retired: bool = False):
        self.db.add(Node(
            id=nid, name=f"test-{nid}", node_type=kind,
            public_ip="127.0.0.1", agent_url="local://test",
            retired_at=datetime.utcnow() if retired else None,
        ))

    def credential(self, sid: int, cid: int, protocol: str,
                   *, active: bool = True, has_config: bool = True):
        self.db.add(ProtocolCredential(
            id=cid, subscription_id=sid, protocol=protocol,
            config_text_encrypted="test-config" if has_config else None,
            is_active=active,
        ))

    def link(self, sid: int, nid: int, lid: int = 1):
        self.db.add(SubscriptionNode(
            id=lid, subscription_id=sid, node_id=nid,
        ))

    @patch("app.services.quota_node_sync._credential_node_ids", return_value={1})
    @patch("app.services.quota_node_sync.build_node_devices")
    def test_only_requested_account_is_validated(self, build, node_ids):
        self.node(1)
        self.credential(40, 1, "wireguard")
        self.credential(40, 2, "v2ray")
        self.credential(41, 3, "wireguard")
        self.db.commit()
        build.return_value = [
            {"subscription_id": 40, "device_id": 6, "identity": "wg", "protocol": "wireguard"},
            {"subscription_id": 40, "device_id": 7, "identity": "xray", "protocol": "xray"},
        ]
        result = quota_refresh._verify_new_subscription_quota_mapping(self.db, 40)
        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "agent-pull-canonical")
        self.assertEqual(len(result["nodes"]), 1)
        build.assert_called_once_with(
            self.db, 1, observed_subscription_ids={40},
        )

    @patch("app.services.quota_node_sync._credential_node_ids", return_value={1})
    @patch("app.services.quota_node_sync.build_node_devices")
    def test_missing_or_revoked_device_cannot_pass_validation(self, build, node_ids):
        self.node(1)
        self.credential(40, 1, "wireguard")
        self.credential(40, 2, "v2ray")
        self.db.commit()
        build.return_value = [
            {"subscription_id": 40, "device_id": 6, "identity": "wg", "protocol": "wireguard"},
        ]
        result = quota_refresh._verify_new_subscription_quota_mapping(self.db, 40)
        self.assertFalse(result["ok"])
        self.assertEqual(result["missing_protocols"], ["xray"])
        build.return_value = [
            {"subscription_id": 40, "device_id": 0, "identity": "wg", "protocol": "wireguard"},
            {"subscription_id": 40, "device_id": 7, "identity": "", "protocol": "xray"},
        ]
        self.assertFalse(quota_refresh._verify_new_subscription_quota_mapping(self.db, 40)["ok"])

    @patch("app.services.quota_node_sync._credential_node_ids", return_value={2})
    @patch("app.services.quota_node_sync.build_node_devices")
    def test_retired_and_iran_nodes_cannot_fake_exit_quota(self, build, node_ids):
        self.node(1, retired=True)
        self.node(2, kind=NodeType.IRAN)
        self.credential(40, 1, "wireguard")
        self.db.commit()
        result = quota_refresh._verify_new_subscription_quota_mapping(self.db, 40)
        self.assertFalse(result["ok"])
        build.assert_not_called()

    @patch("app.services.quota_node_sync._credential_node_ids", return_value=set())
    @patch("app.services.quota_node_sync.build_node_devices")
    def test_legacy_membership_is_preserved(self, build, node_ids):
        self.node(3)
        self.link(40, 3)
        self.credential(40, 1, "openvpn")
        self.db.commit()
        build.return_value = [
            {"subscription_id": 40, "device_id": 9, "identity": "legacy-openvpn", "protocol": "openvpn"}
        ]
        result = quota_refresh._verify_new_subscription_quota_mapping(self.db, 40)
        self.assertTrue(result["ok"])
        build.assert_called_once_with(self.db, 3, observed_subscription_ids={40})

    @patch("app.services.quota_refresh._verify_new_subscription_quota_mapping",
           return_value={"ok": False, "reason": "missing_identity"})
    @patch("app.services.quota_refresh._sync_subscription_quota_nodes_blocking",
           return_value={"ok": False, "mode": "legacy-full"})
    def test_invalid_fast_validation_falls_back_fail_closed(self, old, validator):
        result = quota_refresh._sync_new_subscription_quota_nodes_blocking(self.db, 40)
        self.assertFalse(result["ok"])
        old.assert_called_once_with(self.db, 40, None)

    @patch("app.services.quota_refresh._verify_new_subscription_quota_mapping")
    @patch("app.services.quota_refresh._sync_subscription_quota_nodes_blocking")
    def test_valid_mapping_skips_expensive_full_inventory(self, old, validator):
        validator.return_value = {"ok": True, "mode": "agent-pull-canonical", "nodes": []}
        result = quota_refresh._sync_new_subscription_quota_nodes_blocking(self.db, 40)
        self.assertTrue(result["ok"])
        old.assert_not_called()

    @patch("app.services.quota_refresh._verify_new_subscription_quota_mapping")
    @patch("app.services.quota_refresh._sync_subscription_quota_nodes_blocking",
           return_value={"ok": True, "nodes": []})
    def test_changed_or_removed_node_keeps_original_sync(self, old, validator):
        result = quota_refresh._sync_new_subscription_quota_nodes_blocking(
            self.db, 40, extra_node_ids=[9],
        )
        self.assertTrue(result["ok"])
        validator.assert_not_called()
        old.assert_called_once_with(self.db, 40, [9])

    def test_only_fast_create_opted_in(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        modern = (root / "app/routers/modern_account_delivery_v1.py").read_text()
        quota = (root / "app/services/quota_refresh.py").read_text()
        self.assertIn("fast_validate=prefer_new_singbox_batch", modern)
        self.assertIn("fast_validate: bool = False", quota)


if __name__ == "__main__":
    unittest.main()
