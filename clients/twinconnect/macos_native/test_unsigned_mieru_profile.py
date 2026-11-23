"""Unsigned Mieru must never claim connection from a validated JSON alone."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from unsigned_mieru_profile import (prepare_unsigned_profile,
                                    safe_preflight_summary)
from unsigned_tun_policy import validate_full_tun_config


def fixture():
    return {
        "activeProfile": "fixture", "socks5Port": 1080,
        "socks5ListenLAN": False, "httpProxyListenLAN": False,
        "rpcPort": 8964, "httpProxyPort": 8080,
        "profiles": [{
            "profileName": "fixture",
            "user": {"name": "fixture", "password": "never-print-test"},
            "servers": [{
                "ipAddress": "1.1.1.1", "domainName": "one.one.one.one",
                "portBindings": [{"port": 443, "protocol": "TCP"},
                                 {"port": 443, "protocol": "UDP"}]
            }]
        }]
    }


class MieruUnsignedPreflight(unittest.TestCase):
    def test_profile_is_isolated_to_loopback_without_signing(self):
        original = fixture()
        core, tun = prepare_unsigned_profile(original)
        self.assertEqual(core["rpcPort"], 0)
        self.assertNotIn("httpProxyPort", core)
        self.assertEqual(core["socks5Port"], 17091)
        self.assertEqual(core["profiles"][0]["servers"][0]["domainName"], "")
        self.assertEqual(original["profiles"][0]["servers"][0]["domainName"],
                         "one.one.one.one")
        self.assertEqual(tun["outbounds"][0]["server"], "127.0.0.1")
        self.assertEqual(tun["route"], {
            "final": "proxy", "auto_detect_interface": True})
        self.assertNotIn("route_exclude_address", tun["inbounds"][0])

    def test_tun_candidate_passes_existing_guard_without_route_change(self):
        import json
        core, tun = prepare_unsigned_profile(fixture())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "candidate.json"
            path.write_text(json.dumps(tun))
            self.assertEqual(
                validate_full_tun_config(path)["system_route_modified"], False)

    def test_bad_endpoint_is_rejected(self):
        for value in ("127.0.0.1", "10.0.0.5", "example.org", "::1"):
            bad = fixture()
            bad["profiles"][0]["servers"][0]["ipAddress"] = value
            with self.assertRaises(ValueError):
                prepare_unsigned_profile(bad)

    def test_missing_credentials_and_lan_listener_rejected(self):
        for key, value in (("socks5ListenLAN", True),
                           ("socks5ListenLAN", None)):
            bad = fixture()
            bad[key] = value
            with self.assertRaises(ValueError):
                prepare_unsigned_profile(bad)
        bad = fixture()
        bad["profiles"][0]["user"]["password"] = ""
        with self.assertRaises(ValueError):
            prepare_unsigned_profile(bad)

    def test_profile_not_a_running_connection(self):
        result = safe_preflight_summary(fixture())
        self.assertFalse(result["apple_code_signing_required"])
        self.assertFalse(result["native_core_started"])
        self.assertFalse(result["system_tun_started"])
        self.assertFalse(result["tunnel_connected"])
        self.assertNotIn("password", str(result))


if __name__ == "__main__":
    unittest.main()