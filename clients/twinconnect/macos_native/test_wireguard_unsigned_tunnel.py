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

    def test_twinpanel_two_half_routes_equal_full_ipv4(self):
        import socket
        split = profile().replace("AllowedIPs = 0.0.0.0/0",
                                  "AllowedIPs = 0.0.0.0/1, 128.0.0.0/1")
        with patch.object(socket, "getaddrinfo",
                          return_value=[(None, None, None, None,
                                         ("1.2.3.4", 51820))]):
            config = wg.parse_profile(split)
            self.assertEqual(config["endpoint"], "1.2.3.4:51820")

    def test_twinpanel_two_half_routes_with_ipv6_are_accepted_for_ipv4(self):
        import socket
        split = profile().replace("AllowedIPs = 0.0.0.0/0",
                                  "AllowedIPs = 0.0.0.0/1, 128.0.0.0/1, ::/0")
        with patch.object(socket, "getaddrinfo",
                          return_value=[(None, None, None, None,
                                         ("1.2.3.4", 51820))]):
            self.assertEqual(wg.parse_profile(split)["address"],
                             "10.20.30.15")

    def test_single_half_route_cannot_qualify_as_full_ipv4(self):
        partial = profile().replace("AllowedIPs = 0.0.0.0/0",
                                    "AllowedIPs = 0.0.0.0/1")
        with self.assertRaisesRegex(ValueError, "WG_FULL_IPV4_PROFILE_REQUIRED"):
            wg.parse_profile(partial)

    def test_no_routes_without_full_ipv4_authorization(self):
        text = profile().replace("0.0.0.0/0", "10.0.0.0/8")
        with self.assertRaisesRegex(ValueError, "WG_FULL_IPV4_PROFILE_REQUIRED"):
            wg.parse_profile(text)

    def test_refuses_config_commands_not_in_schema(self):
        with self.assertRaisesRegex(ValueError, "WG_INTERFACE_OPTION_UNSUPPORTED"):
            wg.parse_profile(profile().replace("DNS =", "PostUp = /bin/rm -rf /\nDNS ="))

    def test_amneziawg_profile_preserves_exact_obfuscation(self):
        raw = profile().replace("DNS =", "Jc = 6\nJmin = 8\nJmax = 80\nS1 = 64\nS2 = 96\nH1 = 101\nH2 = 202\nH3 = 303\nH4 = 404\nDNS =")
        with patch.object(wg.socket, "getaddrinfo",
                          return_value=[(None,None,None,None,("1.2.3.4",51820))]):
            data = wg.parse_profile(raw, "amneziawg")
            message = wg.uapi_config(data)
            for item in ("jc=6", "jmin=8", "jmax=80", "s1=64",
                         "s2=96", "h1=101", "h2=202", "h3=303", "h4=404"):
                self.assertIn(item + "\n", message)
            self.assertNotIn("jc=", wg.uapi_config(wg.parse_profile(profile())))
            with self.assertRaisesRegex(ValueError, "WG_INTERFACE_OPTION_UNSUPPORTED"):
                wg.parse_profile(raw)
            with self.assertRaisesRegex(ValueError, "WG_AWG_OBFUSCATION_MISSING"):
                wg.parse_profile(profile(), "amneziawg")
            with self.assertRaisesRegex(ValueError, "WG_AWG_OBFUSCATION_INVALID"):
                wg.parse_profile(raw.replace("H4 = 404", "H4 = 101"), "amneziawg")

    def test_only_root_can_probe(self):
        with patch.object(wg.os, "geteuid", return_value=501):
            with self.assertRaisesRegex(ValueError, "WG_MACOS_ROOT_REQUIRED"):
                wg.probe(profile())


if __name__ == "__main__":
    unittest.main()
