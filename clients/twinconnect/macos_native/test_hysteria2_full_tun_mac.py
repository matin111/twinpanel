"""Hysteria2 uses actual system TUN, not a SOCKS listener, on macOS."""
from pathlib import Path
import json
import tempfile
import unittest
import sys

DIR = Path(__file__).parent
sys.path.insert(0, str(DIR))
from unsigned_tun_policy import validate_full_tun_config

DIRECTORY = (DIR / "TwinConnectMacOSNativeDirectory.swift").read_text()
DASHBOARD = (DIR / "TwinConnectMacOSNativeDashboard.swift").read_text()


class Hysteria2TUNTests(unittest.TestCase):
    def test_darwin_tun_interface_is_auto_allocated(self):
        begin = DIRECTORY.index('func prepareFullTUNCandidate(')
        end = DIRECTORY.index('private func localHysteria2Config(', begin)
        code = DIRECTORY[begin:end]
        self.assertIn('"auto_route": true', code)
        self.assertIn('"auto_detect_interface": true', code)
        self.assertNotIn('"interface_name": "twinconnect"', code)
        self.assertIn('Darwin allocates utunN', code)
        self.assertIn('let outbounds = proxy["outbounds"]', code)

    def test_offline_hysteria2_preflight_uses_valid_darwin_interface(self):
        begin = DIRECTORY.index('func prepareUnroutedHysteria2TUN(')
        end = DIRECTORY.index('func prepareFullTUNCandidate(', begin)
        self.assertNotIn('"interface_name": "twinconnect-test"', DIRECTORY[begin:end])
        self.assertIn('"auto_route": false', DIRECTORY[begin:end])

    def test_hysteria2_is_routed_through_root_tun(self):
        self.assertIn('"hysteria2", "tuic", "anytls"', DIRECTORY)
        self.assertIn('directory.prepareFullTUNCandidate(session, serverID: serverID,', DASHBOARD)
        self.assertIn('startFullTun(session, serverID: serverID, protocolCode: selectedProtocol)', DASHBOARD)
        self.assertIn('activeProtocol == "hysteria2"', DASHBOARD)

    def test_canonical_hysteria2_config_passes_policy_without_unsafe_interface(self):
        config = {
            "log": {"level": "error"},
            "inbounds": [{"type": "tun", "tag": "twinconnect-tun",
                          "address": ["172.19.0.1/30"], "auto_route": True,
                          "auto_redirect": False, "strict_route": False,
                          "stack": "system"}],
            "outbounds": [{"type": "hysteria2", "tag": "proxy",
                           "server": "example.org", "server_port": 443,
                           "password": "fixture-not-a-real-secret",
                           "tls": {"enabled": True, "server_name": "example.org"}}],
            "route": {"final": "proxy", "auto_detect_interface": True}
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "profile.json"
            path.write_text(json.dumps(config))
            result = validate_full_tun_config(path)
            self.assertEqual(result["mode"], "full_tun_candidate")
            self.assertNotIn("interface_name", config["inbounds"][0])


if __name__ == "__main__":
    unittest.main()