"""Regression tests for per-node protocol operator controls.

The controls must never stop a daemon, delete a credential, change a node's
global visibility, or affect a different protocol/node. SQLite-only.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Node, NodeType
from app.node_protocol_operator_switches_v1 import (
    NodeProtocolOperatorSwitch, disabled_pairs, filter_public_delivery,
    is_disabled, set_disabled,
)


class PerNodeProtocolSwitchTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Node.__table__.create(self.engine)
        NodeProtocolOperatorSwitch.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([
            Node(id=1, name="Exit A", node_type=NodeType.EXIT,
                 public_ip="192.0.2.1", agent_url="https://test.invalid"),
            Node(id=2, name="Exit B", node_type=NodeType.EXIT,
                 public_ip="192.0.2.2", agent_url="https://test.invalid"),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_single_node_and_protocol_are_isolated_and_reversible(self):
        self.assertFalse(is_disabled(self.db, 1, "wireguard"))
        self.assertTrue(set_disabled(self.db, 1, "WireGuard", True))
        self.db.commit()
        self.assertTrue(is_disabled(self.db, 1, "wireguard"))
        self.assertFalse(is_disabled(self.db, 1, "cisco"))
        self.assertFalse(is_disabled(self.db, 2, "wireguard"))
        self.assertEqual(disabled_pairs(self.db), {(1, "wireguard")})
        self.assertEqual(disabled_pairs(self.db, [2]), set())
        self.assertFalse(set_disabled(self.db, 1, "wireguard", False))
        self.db.commit()
        self.assertFalse(is_disabled(self.db, 1, "wireguard"))
        self.assertEqual(disabled_pairs(self.db), set())

    def test_protocol_alias_is_canonicalized(self):
        set_disabled(self.db, 2, "naiveproxy", True)
        self.db.commit()
        self.assertTrue(is_disabled(self.db, 2, "naive"))

    def test_one_disabled_pair_removes_direct_and_tunnel_items_only(self):
        self.db.add(NodeProtocolOperatorSwitch(
            node_id=1, protocol="wireguard", disabled=True))
        self.db.commit()
        original = {
            "subscription_id": 77,
            "credentials": [
                {"protocol": "wireguard", "username": "a",
                 "items": [
                    {"node_id": 1, "uri": "wg://direct", "delivery_mode": "direct"},
                    {"node_id": 1, "uri": "wg://tunnel", "delivery_mode": "tunnel"},
                    {"node_id": 2, "uri": "wg://other"},
                ]},
                {"protocol": "cisco", "items": {"node_id": 1, "config": "oc"}},
                {"protocol": "v2ray", "items": {"node_id": 2, "uri": "vless://"}},
            ],
        }
        out = filter_public_delivery(self.db, original)
        self.assertEqual(len(out["credentials"]), 3)
        self.assertEqual(out["credentials"][0]["items"], [{"node_id": 2, "uri": "wg://other"}])
        self.assertEqual(out["credentials"][1], original["credentials"][1])
        self.assertEqual(len(original["credentials"][0]["items"]), 3)
        self.assertIsNot(out, original)

    def test_single_item_and_empty_credential_are_removed(self):
        set_disabled(self.db, 1, "v2ray", True)
        self.db.commit()
        payload = {"credentials": [
            {"protocol": "v2ray", "items": {"node_id": 1, "uri": "vless://old"}},
            {"protocol": "v2ray", "items": [{"node_id": 2, "uri": "vless://new"}]},
            {"protocol": "wireguard", "items": {"node_id": 1, "config": "wg"}},
        ]}
        out = filter_public_delivery(self.db, payload)
        self.assertEqual(len(out["credentials"]), 2)
        self.assertEqual(out["credentials"][0]["items"], [{"node_id": 2, "uri": "vless://new"}])

    def test_untouched_payload_keeps_identity_and_settings(self):
        payload = {"credentials": [{"protocol": "cisco", "items": {"node_id": 1}}]}
        self.assertIs(filter_public_delivery(self.db, payload), payload)
        set_disabled(self.db, 2, "wireguard", True)
        self.db.commit()
        self.assertIs(filter_public_delivery(self.db, payload), payload)

    def test_unknown_protocol_rejected_without_db_write(self):
        with self.assertRaises(ValueError):
            set_disabled(self.db, 1, "malicious-unit; shutdown", True)
        self.assertEqual(disabled_pairs(self.db), set())

    def test_central_scope_excludes_only_blocked_protocol(self):
        from app.services.central_partial_protocol_scope_v1 import node_supported_protocols
        from app.protocol_account_registry import ALL_PROTOCOL_SET
        set_disabled(self.db, 1, "cisco", True)
        self.db.commit()
        available = node_supported_protocols(self.db, 1)
        self.assertEqual(available, ALL_PROTOCOL_SET - {"cisco"})
        self.assertEqual(node_supported_protocols(self.db, 2), ALL_PROTOCOL_SET)

    def test_api_auth_and_source_contracts(self):
        from app.routers.node_protocol_operator_controls_v1 import (
            read_switch, write_switch, router,
        )
        self.assertIn("require_admin", repr(router.dependencies[0]))
        source = (Path(__file__).resolve().parents[1] /
                  "app/routers/modern_protocol_admin_v3.py").read_text()
        self.assertIn('"/modern-protocols/{node_id}/{protocol}/restart"', source)
        self.assertIn("exclusive_node_install(node_id)", source)
        self.assertIn('"twinpanel-sing-box.service"', source)
        self.assertIn('"twinpanel-trusttunnel.service"', source)

    def test_frontend_confirmation_and_node_actions(self):
        source = (Path(__file__).resolve().parents[2] /
                  "components/protocol-command-center.tsx").read_text()
        for fragment in (
            "restartOnNode", "toggleOnNode", "window.confirm(",
            "/v1/admin/node-protocol-controls/",
            "operatorDisabled", "nodeActions",
            "ری‌استارت پروتکل", "غیرفعال روی نود",
        ):
            self.assertIn(fragment, source)


if __name__ == "__main__":
    unittest.main()
