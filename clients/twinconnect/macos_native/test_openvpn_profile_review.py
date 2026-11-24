"""Offline OpenVPN profile safety tests. Never run OpenVPN or edit routes."""
from pathlib import Path
import importlib.util
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "openvpn_profile_review", HERE / "openvpn_profile_review.py")
reviewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reviewer)

SAFE = """client
dev tun
proto udp
remote vpn.example.com 1194
remote-cert-tls server
auth SHA256
<ca>
-----BEGIN CERTIFICATE-----
TEST_CERT_FOR_PARSER_ONLY
-----END CERTIFICATE-----
</ca>
"""


class OpenVPNReviewTests(unittest.TestCase):
    def test_approved_profile_has_no_routes(self):
        result = reviewer.review(SAFE)
        self.assertEqual(result["state"], "reviewed_unrouted_candidate")
        self.assertFalse(result["connected"])
        self.assertFalse(result["route_changed"])
        self.assertEqual(result["remotes"], 1)

    def test_remote_cert_tls_requires_server(self):
        with self.assertRaises(ValueError):
            reviewer.review(SAFE.replace("remote-cert-tls server", "remote-cert-tls"))
        with self.assertRaises(ValueError):
            reviewer.review(SAFE.replace("remote-cert-tls server", "remote-cert-tls client"))

    def test_rejects_script_execution(self):
        for directive in (
                "script-security 2", "up /bin/sh", "plugin /tmp/evil.dylib",
                "setenv PATH /tmp", "config /tmp/a.ovpn", "management 127.0.0.1 5555"):
            with self.subTest(directive=directive), self.assertRaises(ValueError):
                reviewer.review(SAFE + directive + "\n")

    def test_rejects_server_route_injection(self):
        for directive in ("redirect-gateway local", "route 0.0.0.0 0.0.0.0",
                          "dhcp-option DNS 8.8.8.8", "pull-filter ignore route"):
            with self.subTest(directive=directive), self.assertRaises(ValueError):
                reviewer.review(SAFE + directive + "\n")

    def test_twinpanel_export_is_reviewed_with_default_route_removed(self):
        export = SAFE + (
            "nobind\n"
            "persist-key\n"
            "persist-tun\n"
            "data-ciphers AES-256-GCM:AES-128-GCM\n"
            "mssfix 1300\n"
            "tun-mtu 1500\n"
            "resolv-retry infinite\n"
            "verb 3\n"
            "redirect-gateway def1\n"
        )
        result = reviewer.review(export)
        self.assertEqual(result["state"], "reviewed_unrouted_candidate")
        self.assertIn("redirect-gateway", result["stripped"])
        self.assertFalse(any(x.startswith("redirect-gateway")
                             for x in result["directives"]))

    def test_rejects_out_of_range_transport_values(self):
        for directive in ("mssfix 99999", "tun-mtu -1", "verb 9",
                          "resolv-retry 999999", "redirect-gateway def1 local"):
            with self.subTest(directive=directive), self.assertRaises(ValueError):
                reviewer.review(SAFE + directive + "\n")

    def test_rejects_unsupported_directive_and_file_paths(self):
        for directive in ("ca /tmp/ca.pem", "key /tmp/key.pem",
                          "auth-user-pass /tmp/auth.txt", "tls-auth /tmp/auth.key"):
            with self.subTest(directive=directive), self.assertRaises(ValueError):
                reviewer.review(SAFE + directive + "\n")

    def test_rejects_untrusted_remote_and_missing_ca(self):
        with self.assertRaises(ValueError):
            reviewer.review(SAFE.replace("vpn.example.com", "127.0.0.1"))
        with self.assertRaises(ValueError):
            reviewer.review(SAFE.split("<ca>")[0])

    def test_rejects_nested_inline_material(self):
        with self.assertRaises(ValueError):
            reviewer.review(SAFE.replace("TEST_CERT_FOR_PARSER_ONLY", "<key>"))

    def test_rejects_control_chars_and_oversize(self):
        with self.assertRaises(ValueError):
            reviewer.review(SAFE + "\x00")
        with self.assertRaises(ValueError):
            reviewer.review(SAFE + "x" * 66000)


if __name__ == "__main__":
    unittest.main()
