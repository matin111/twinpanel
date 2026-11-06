"""Opt-in delivery contract: V2Ray is untouched; legacy remains default."""
import base64
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.routers.public_connection_protocol_subscriptions_v30 import (
    _protocol_uris_from_payload,
)


class CentralModernDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.sub = SimpleNamespace(account_username="person", id=123)
        self.payload = {"credentials": [
            {"protocol": "anytls", "items": [{
                "node_id": 12, "uri": "anytls://stale",
                "outbound": {
                    "type": "anytls", "server": "old.example.org",
                    "server_port": 443, "password": "secret",
                    "tls": {"enabled": True, "server_name": "original.example.org"},
                },
            }]},
        ]}

    def test_legacy_without_db(self):
        uri = _protocol_uris_from_payload(self.sub, self.payload, "anytls")[0]
        self.assertIn("old.example.org:443", uri)

    @patch("app.routers.public_connection_protocol_subscriptions_v30.applied_modern_connection")
    def test_explicit_connection_changes_only_endpoint(self, lookup):
        lookup.return_value = {"host": "new.example.org", "port": 8443}
        uri = _protocol_uris_from_payload(self.sub, self.payload, "anytls", db=object())[0]
        self.assertIn("new.example.org:8443", uri)
        self.assertIn("secret@", uri)
        self.assertIn("sni=original.example.org", uri)

    @patch("app.routers.public_connection_protocol_subscriptions_v30.applied_modern_connection")
    def test_no_applied_connection_keeps_old_behavior(self, lookup):
        lookup.return_value = None
        uri = _protocol_uris_from_payload(self.sub, self.payload, "anytls", db=object())[0]
        self.assertIn("old.example.org:443", uri)

    @patch("app.routers.public_connection_protocol_subscriptions_v30.applied_modern_connection")
    def test_incompatible_projection_does_not_leak_stale_uri(self, lookup):
        lookup.return_value = {"host": "new.example.org", "port": 8443}
        payload = {"credentials": [{"protocol": "anytls", "items": [
            {"node_id": 12, "uri": "anytls://secret@old.example.org:443/"}
        ]}]}
        self.assertEqual(
            _protocol_uris_from_payload(self.sub, payload, "anytls", db=object()), []
        )

    def test_v2ray_bypasses_projection(self):
        payload = {"credentials": [{"protocol": "v2ray", "items": [
            {"uri": "vless://example@old.example.org:443#old"}
        ]}]}
        with patch("app.routers.public_connection_protocol_subscriptions_v30.applied_modern_connection") as lookup:
            self.assertEqual(
                _protocol_uris_from_payload(self.sub, payload, "v2ray", db=object()),
                ["vless://example@old.example.org:443#old"],
            )
            lookup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
