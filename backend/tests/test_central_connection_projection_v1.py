"""No runtime credentials or server mutations are permitted in projection."""
import json
import unittest

from app.services.central_connection_projection_v1 import (
    ConnectionProjectionError,
    project_singbox_item,
)


class CentralConnectionProjectionTests(unittest.TestCase):
    def test_immutable_credential_and_consistent_outputs(self):
        original = {
            "uri": "anytls://old",
            "outbound": {
                "type": "anytls", "server": "old.example.org",
                "server_port": 443, "password": "USER-SECRET",
                "tls": {"enabled": True, "server_name": "old-sni.example.org"},
            },
            "config": json.dumps({"outbounds": [
                {"type": "direct", "tag": "direct"},
                {"type": "anytls", "server": "old.example.org",
                 "server_port": 443, "password": "USER-SECRET",
                 "tls": {"enabled": True, "server_name": "old-sni.example.org"}},
            ]}),
        }
        changed = project_singbox_item(
            "anytls", original,
            {"host": "new.example.org", "port": 8443, "sni": "new-sni.example.org"},
        )
        self.assertEqual(original["outbound"]["server"], "old.example.org")
        self.assertNotIn("uri", changed)
        for out in (changed["outbound"], json.loads(changed["config"])["outbounds"][1]):
            self.assertEqual(out["server"], "new.example.org")
            self.assertEqual(out["server_port"], 8443)
            self.assertEqual(out["tls"]["server_name"], "new-sni.example.org")
            self.assertEqual(out["password"], "USER-SECRET")

    def test_reject_unsafe_host(self):
        with self.assertRaises(ConnectionProjectionError):
            project_singbox_item("anytls", {"outbound": {"type": "anytls"}},
                                 {"host": "example.org/path"})

    def test_does_not_mutate_or_render_wireguard(self):
        with self.assertRaises(ConnectionProjectionError):
            project_singbox_item("wireguard", {"private_key": "secret"}, {"host": "x.org"})

    def test_invalid_tls_rejected(self):
        with self.assertRaises(ConnectionProjectionError):
            project_singbox_item("anytls", {"outbound": {"type": "anytls"}},
                                 {"sni": "new.example.org"})


if __name__ == "__main__":
    unittest.main()
