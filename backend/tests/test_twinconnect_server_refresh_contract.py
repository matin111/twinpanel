"""Regression: server refresh must be scoped to the authorized app account."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
ROUTES = ROOT / "backend/app/routers/central_app_credentials_v1.py"


class ServerRefreshContract(unittest.TestCase):
    def test_authenticated_profile_endpoint_uses_bearer_session_not_share_token(self):
        source = ROUTES.read_text(encoding="utf-8")
        route = source.split('@router.post("/session/profiles")', 1)[1].split(
            '@router.post("/admin/subscriptions/', 1)[0]
        self.assertIn("Depends(_session_subscription)", route)
        self.assertIn("_profiles_for_verified_subscription(sub, payload.protocol, db)", route)
        self.assertNotIn("_share_token(sub)", route)
        self.assertNotIn("subscription_protocol_profiles(", route)
        public = (ROOT / "backend/app/routers/central_app_v1.py").read_text(encoding="utf-8")
        self.assertIn("def _profiles_for_verified_subscription(", public)
        self.assertIn("_xray_payload_for_verified_subscription(sub, db)", public)
        v7 = (ROOT / "backend/app/routers/public_connection_multilink_v7.py").read_text(encoding="utf-8")
        self.assertIn("def _xray_payload_for_verified_subscription(", v7)
        self.assertIn("return sub, _xray_payload_for_verified_subscription(sub, db)", v7)

    def test_authenticated_inventory_only_contains_assigned_visible_nodes(self):
        src = ROUTES.read_text(encoding="utf-8")
        route = src.split('@router.get("/session/servers")', 1)[1].split(
            '@router.post("/session/profiles")', 1
        )[0]
        self.assertIn("Depends(_session_subscription)", route)
        self.assertIn("SubscriptionNode.node_id == Node.id", route)
        self.assertIn("SubscriptionNode.subscription_id == sub.id", route)
        self.assertIn("Node.show_to_users.is_(True)", route)
        self.assertIn("Node.retired_at.is_(None)", route)
        self.assertIn("subscription_app_namespace(db, sub)", route)
        self.assertIn('"latency_ms": None', route)
        # A validated global probe IP is intentionally returned only for
        # nodes already assigned to this authenticated subscription.
        self.assertIn('"probe_ip": _public_node_probe_ip(node.public_ip)', route)
        self.assertIn('address.is_global', src)
        for secret in ('"public_ip":', '"public_domain":', '"agent_url":',
                       '"secret_encrypted":', '"config_text_encrypted":'):
            self.assertNotIn(secret, route)


if __name__ == "__main__":
    unittest.main()
