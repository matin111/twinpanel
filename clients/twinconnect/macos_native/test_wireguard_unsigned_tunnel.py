"""Offline regression tests: no real WireGuard peer or route is touched."""
import base64
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "unsigned_wg", Path(__file__).with_name("wireguard_unsigned_tunnel.py"))
wg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wg)


def profile():
    private = base64.b64encode(b"a" * 32).decode()
    public = base64.b64encode(b"b" * 32).decode()
    return (f"[Interface]\nPrivateKey = {private}\nAddress = 10.20.30.15/32\n"
            f"DNS = 1.1.1.1\n\n[Peer]\nPublicKey = {public}\n"
            f"Endpoint = tunnel.example.com:51820\nAllowedIPs = 0.0.0.0/0\n")


class UnsignedWireGuardTests(unittest.TestCase):
    def test_valid_profile_does_not_touch_routes(self):
        info = [(None, None, None, None, ("203.0.113.3", 51820))]
        # Mock with a genuine public IPv4 instead of documentation ranges.
        info[0] = (None, None, None, None, ("1.2.3.4", 51820))
        with patch.object(wg.socket, "getaddrinfo", return_value=info), \
             patch.object(wg.subprocess, "run") as command:
            parsed = wg.parse_profile(profile())
            self.assertEqual(parsed["address"], "10.20.30.15")
            self.assertEqual(parsed["endpoint"], "1.2.3.4:51820")
            self.assertEqual(len(parsed["private"]), 64)
            self.assertIn("allowed_ip=0.0.0.0/0", wg.uapi_config(parsed))
            command.assert_not_called()

    def test_reject_bad_key_and_no_peer(self):
        with self.assertRaisesRegex(ValueError, "WG_INVALID_KEY"):
            wg.parse_profile(profile().replace("a" * 0 + base64.b64encode(b"a"*32).decode(),
                                              "not-a-key"))
        with self.assertRaisesRegex(ValueError, "WG_SINGLE_PEER_REQUIRED"):
            wg.parse_profile(profile().replace("[Peer]", "[Invalid]"))

    def test_no_routes_without_full_ipv4_authorization(self):
        text = profile().replace("0.0.0.0/0", "10.0.0.0/8")
        with self.assertRaisesRegex(ValueError, "WG_FULL_IPV4_PROFILE_REQUIRED"):
            wg.parse_profile(text)

    def test_refuses_config_commands_not_in_schema(self):
        with self.assertRaisesRegex(ValueError, "WG_INTERFACE_OPTION_UNSUPPORTED"):
            wg.parse_profile(profile().replace("DNS =", "PostUp = /bin/rm -rf /\nDNS ="))

    def test_only_root_can_probe(self):
        with patch.object(wg.os, "geteuid", return_value=501):
            with self.assertRaisesRegex(ValueError, "WG_MACOS_ROOT_REQUIRED"):
                wg.probe(profile())


if __name__ == "__main__":
    unittest.main()
