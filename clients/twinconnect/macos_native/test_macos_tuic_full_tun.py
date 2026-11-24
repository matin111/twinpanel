"""Reviewed TUIC route and live-panel option preservation contracts."""
from pathlib import Path
import json
import subprocess
import unittest

ROOT = Path(__file__).parent
DIR = (ROOT / "TwinConnectMacOSNativeDirectory.swift").read_text()
UI = (ROOT / "TwinConnectMacOSNativeDashboard.swift").read_text()
ENGINE = ROOT / "build/singbox/amd64/sing-box"


class TUICMacTUNTests(unittest.TestCase):
    def test_tuic_profile_checks_real_quic_options(self):
        code = DIR[DIR.index('if protocolCode == "tuic" {'):
                   DIR.index('} else if protocolCode == "anytls" {')]
        self.assertIn('reviewed["uuid"] = uuid', code)
        self.assertIn('reviewed["heartbeat"] = hb', code)
        self.assertIn('reviewed["zero_rtt_handshake"] = zeroRTT', code)
        self.assertIn('outbound["heartbeat"] != nil { return nil }', code)
        self.assertIn('outbound["zero_rtt_handshake"] != nil { return nil }', code)
        self.assertIn('congestion_control', code)

    def test_tuic_entitlement_and_same_server_profile(self):
        self.assertIn('"tuic", "anytls", "socks5"', DIR)
        self.assertIn('let matches = items.filter { item in', DIR)
        self.assertIn('let config = self.reviewedSingBoxProxyConfig(', DIR)
        self.assertIn('directory.prepareFullTUNCandidate(session, serverID: serverID,', UI)
        self.assertIn('startFullTun(session, serverID: serverID, protocolCode: selectedProtocol)', UI)

    def test_macos_tun_has_no_fixed_interface_name(self):
        code = DIR[DIR.index('func prepareFullTUNCandidate('):
                   DIR.index('private func localHysteria2Config(')]
        self.assertNotIn('"interface_name": "twinconnect"', code)
        self.assertIn('"auto_route": true', code)
        self.assertIn('"auto_detect_interface": true', code)

    def test_installed_singbox_accepts_fixture_tuic_config(self):
        if not ENGINE.is_file():
            self.skipTest('sing-box is not installed in this test environment')
        config = {
            'log': {'level': 'error'},
            'inbounds': [{'type': 'tun', 'tag': 'twinconnect-tun',
                'address': ['172.19.0.1/30'], 'auto_route': True,
                'auto_redirect': False, 'strict_route': False, 'stack': 'system'}],
            'outbounds': [{'type': 'tuic', 'tag': 'proxy',
                'server': 'example.org', 'server_port': 443,
                'uuid': '10000000-0000-4000-8000-000000000001',
                'password': 'test-fixture-not-a-secret',
                'tls': {'enabled': True, 'server_name': 'example.org'},
                'congestion_control': 'bbr', 'heartbeat': '10s',
                'zero_rtt_handshake': False}],
            'route': {'final': 'proxy', 'auto_detect_interface': True},
        }
        result = subprocess.run(
            [str(ENGINE), 'check', '-c', '/dev/stdin'],
            input=json.dumps(config), capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0,
                         'installed sing-box rejected the safe TUIC fixture')


if __name__ == '__main__':
    unittest.main()