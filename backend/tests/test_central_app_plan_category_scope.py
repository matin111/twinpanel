"""Regression: a customer's app catalogue comes only from their panel plan."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / "app" / "central_app_plan_policy.py"
SPEC = importlib.util.spec_from_file_location("central_app_plan_policy_test", MODULE)
assert SPEC and SPEC.loader
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


class PlanScopeTests(unittest.TestCase):
    def test_vitory_with_legacy_sixteen_rows_is_only_two_protocols(self):
        all_protocols = {
            "v2ray", "hysteria2", "wireguard", "cisco",
            "openvpn", "l2tp", "tuic", "anytls", "socks5",
            "naive", "shadowtls", "snell", "mieru", "sudoku",
            "trusttunnel", "amneziawg",
        }
        self.assertEqual(POLICY.category_protocols("اشتراک ویتوری", all_protocols),
                         {"v2ray", "hysteria2"})
        self.assertEqual(POLICY.category_protocols("V2Ray", all_protocols),
                         {"v2ray", "hysteria2"})

    def test_vitory_uses_stricter_admin_protocol_selection(self):
        self.assertEqual(POLICY.category_protocols("ویتوری", {"v2ray"}),
                         {"v2ray"})
        self.assertEqual(POLICY.category_protocols("ویتوری", set()),
                         {"v2ray", "hysteria2"})

    def test_special_uses_panel_protocol_template_unmodified(self):
        allowed = {"cisco", "openvpn", "v2ray", "hysteria2"}
        self.assertEqual(POLICY.category_protocols("اشتراک ویژه", allowed),
                         allowed)
        self.assertEqual(POLICY.category_protocols("ویژه", set()), set())

    def test_no_credentials_or_server_address_in_policy(self):
        source = MODULE.read_text(encoding="utf-8")
        for secret in ("account_password", "share_token", "secret_encrypted",
                       "db.commit", "agent_url"):
            self.assertNotIn(secret, source)

    def test_authenticated_app_catalog_does_not_require_share_link(self):
        route = (Path(__file__).resolve().parents[1] / "app" / "routers" /
                 "central_app_credentials_v1.py").read_text(encoding="utf-8")
        block = route.split('@router.get("/session/protocols")', 1)[1].split(
            '@router.get("/session/plan")', 1)[0]
        self.assertIn("Depends(_session_subscription)", block)
        self.assertIn("_selected_client_protocols(db, sub.id)", block)
        self.assertIn("ProtocolCredential.subscription_id == sub.id", block)
        self.assertIn("protocol_catalog(selected, configured)", block)
        self.assertNotIn("_share_token(sub)", block)
        self.assertNotIn("subscription_protocol_catalog(", block)

    def test_api_enforces_plan_category_on_protocols_profiles_and_nodes(self):
        root = Path(__file__).resolve().parents[1] / "app" / "routers"
        api = (root / "central_app_v1.py").read_text(encoding="utf-8")
        auth = (root / "central_app_credentials_v1.py").read_text(encoding="utf-8")
        self.assertIn("category_protocols(", api)
        self.assertIn("selected & permitted if permitted else selected", api)
        self.assertIn("protocol not in _selected_client_protocols(db, sub.id)", api)
        self.assertIn("protocol_catalog(selected, configured)", api)
        self.assertIn("PlanNode.plan_id == int(sub.plan_id)", auth)
        self.assertIn("SubscriptionNode.subscription_id == sub.id", auth)
        self.assertIn("Node.id.in_(configured_node_ids)", auth)


if __name__ == "__main__":
    unittest.main()
