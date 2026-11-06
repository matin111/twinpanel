"""Contract tests for optional centrally resolved share-URI generation."""
import copy
import unittest
from urllib.parse import parse_qs, urlsplit

from app.routers.public_connection_modern_import_v15 import standard_share_uri


class CentralModernURIContractTests(unittest.TestCase):
    def test_anytls_projected_without_changing_password(self):
        item = {"outbound": {
            "type": "anytls", "server": "old.example.org", "server_port": 443,
            "password": "private-pass",
            "tls": {"enabled": True, "server_name": "old-sni.example.org"},
        }}
        original = copy.deepcopy(item)
        uri = standard_share_uri(
            "anytls", item, "Account",
            applied_connection={"host": "new.example.org", "port": 8443, "sni": "new-sni.example.org"},
        )
        parts = urlsplit(uri)
        self.assertEqual(parts.scheme, "anytls")
        self.assertEqual(parts.hostname, "new.example.org")
        self.assertEqual(parts.port, 8443)
        self.assertEqual(parts.username, "private-pass")
        self.assertEqual(parse_qs(parts.query)["sni"], ["new-sni.example.org"])
        self.assertEqual(item, original)

    def test_legacy_unchanged_without_explicit_projection(self):
        item = {"outbound": {
            "type": "hysteria2", "server": "old.example.org", "server_port": 443,
            "password": "private-pass", "tls": {"server_name": "old.example.org"},
        }}
        self.assertEqual(
            standard_share_uri("hysteria2", item, "Account"),
            standard_share_uri("hysteria2", item, "Account", applied_connection=None),
        )


if __name__ == "__main__":
    unittest.main()
