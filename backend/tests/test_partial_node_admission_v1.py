"""New Exits may serve verified protocols while failed ones remain unavailable."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import NodeType
from app.protocol_account_registry import ALL_PROTOCOL_KEYS
from app.services.central_partial_protocol_scope_v1 import node_supported_protocols
from app.services.new_node_readiness_v1 import verify_new_exit_readiness


class PartialNodeScopeTests(unittest.TestCase):
    def test_verified_fifteen_without_xray(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = SimpleNamespace(
            expected_protocols=16, installed_protocols=15, stage="verified_ready",
        )
        db.query.return_value.filter.return_value.all.return_value = [
            SimpleNamespace(protocol=k) for k in ALL_PROTOCOL_KEYS if k != "v2ray"
        ]
        allowed = node_supported_protocols(db, 27)
        self.assertEqual(len(allowed), 15)
        self.assertNotIn("v2ray", allowed)

    def test_failed_install_is_never_admitted(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = SimpleNamespace(
            expected_protocols=16, installed_protocols=15, stage="failed",
        )
        with self.assertRaisesRegex(RuntimeError, "NOT_VERIFIED"):
            node_supported_protocols(db, 27)


class LivePartialReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_xray_does_not_block_healthy_fifteen(self):
        db = MagicMock()
        db.get.return_value = SimpleNamespace(
            id=27, retired_at=None, node_type=NodeType.EXIT,
        )
        db.query.return_value.filter.return_value.all.return_value = [
            SimpleNamespace(protocol=k, status="online", port=8443)
            for k in ALL_PROTOCOL_KEYS if k != "v2ray"
        ]
        conn = MagicMock()
        conn.wait_closed = AsyncMock()
        with (
            patch("app.services.new_node_readiness_v1.connect_protocol_runtime",
                  new_callable=AsyncMock, return_value=conn),
            patch("app.services.new_node_readiness_v1._protocol_live_health",
                  new_callable=AsyncMock, return_value={"ok": True}),
            patch("app.services.new_node_readiness_v1.profile_health",
                  new_callable=AsyncMock, return_value={"ok": True}),
        ):
            result = await verify_new_exit_readiness(
                db, 27, require_tls_profiles=True, allow_partial=True,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["ready_count"], 15)
        self.assertEqual(result["missing"], ["v2ray"])
        self.assertNotIn("v2ray", result["ready_protocols"])

    async def test_strict_behavior_unchanged(self):
        db = MagicMock()
        db.get.return_value = SimpleNamespace(
            id=27, retired_at=None, node_type=NodeType.EXIT,
        )
        db.query.return_value.filter.return_value.all.return_value = [
            SimpleNamespace(protocol=k, status="online", port=8443)
            for k in ALL_PROTOCOL_KEYS if k != "v2ray"
        ]
        result = await verify_new_exit_readiness(db, 27)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "protocol_not_installed")


if __name__ == "__main__":
    unittest.main()
