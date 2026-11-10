"""Regression: server refresh must be scoped to the authorized app account."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
ROUTES = ROOT / "backend/app/routers/central_app_credentials_v1.py"


class ServerRefreshContract(unittest.TestCase):
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
