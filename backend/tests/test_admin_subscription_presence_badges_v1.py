"""Ensure the admin subscription cards keep network presence separate from status."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.routers import subscription_admin_v2 as admin
from app.routers.runtime_endpoints import _live_item


class AdminSubscriptionPresenceTests(unittest.TestCase):
    def setUp(self):
        self.sub = SimpleNamespace(id=519, status="ACTIVE")

    def item(self, states):
        with patch.object(admin, "_enriched_payload_from_context", return_value={
            "id": 519, "status": "active", "account_username": "sample",
        }):
            return admin._admin_page_item_with_presence(self.sub, {}, states)

    def test_confirmed_online_keeps_commercial_status(self):
        states = {519: {
            "online": True, "protocols": {"wireguard"},
            "last_seen_at": None,
        }}
        payload = self.item(states)
        self.assertTrue(payload["is_online"])
        self.assertEqual(payload["presence_state"], "online")
        self.assertEqual(payload["status"], "active")

    def test_offline_does_not_mark_subscription_suspended(self):
        payload = self.item({})
        self.assertFalse(payload["is_online"])
        self.assertEqual(payload["presence_state"], "offline")
        self.assertEqual(payload["status"], "active")

    def test_stale_telemetry_is_unknown_not_false_offline(self):
        payload = self.item({519: {
            "online": False, "protocols": set(),
            "last_seen_at": None,
            "uncertain_protocols": {"openvpn"},
        }})
        self.assertFalse(payload["is_online"])
        self.assertEqual(payload["presence_state"], "unknown")
        self.assertEqual(payload["status"], "active")

    def test_existing_live_snapshot_policy_remains_authoritative(self):
        state = _live_item(519, {519: {
            "online": True, "protocols": {"ocserv"},
            "last_seen_at": None,
        }})
        self.assertTrue(state["online"])
        self.assertEqual(state["presence_state"], "online")


if __name__ == "__main__":
    unittest.main()
