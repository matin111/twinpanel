"""Verify the real macOS AnyTLS profile and offline TUN compatibility."""
from pathlib import Path
import json
import subprocess
import unittest

BASE = Path(__file__).parent
DIRECTORY = (BASE / "TwinConnectMacOSNativeDirectory.swift").read_text()
DASHBOARD = (BASE / "TwinConnectMacOSNativeDashboard.swift").read_text()
ENGINE = BASE / "build/singbox/amd64/sing-box"


class AnyTLSTunTests(unittest.TestCase):
    def test_anytls_outbound_rejects_malformed_options_not_silent_strip(self):
        a = DIRECTORY.index('} else if protocolCode == "anytls" {')
        b = DIRECTORY.index('        let config: [String: Any] = [', a)
        section = DIRECTORY[a:b]
        self.assertIn('reviewed["idle_session_check_interval"]', section.replace('reviewed[key]', 'reviewed["idle_session_check_interval"]'))
        self.assertIn('reviewed["min_idle_session"] = idle', section)
        self.assertIn('outbound["min_idle_session"] != nil { return nil }', section)
        self.assertIn('outbound[key] != nil { return nil }', section)
        self.assertIn('outbound["min_idle_session"] is Bool', section)
        self.assertIn('reviewed["client_metadata"] = metadata', section)
        self.assertIn('outbound["disable_reuse"] == nil', section)
        self.assertIn('outbound["network"] == nil', section)

    def test_anytls_entitlement_and_real_system_tun(self):
        self.assertIn('"tuic", "anytls", "socks5"', DIRECTORY)
        self.assertIn('"hysteria2", "tuic", "anytls"', DIRECTORY)
        self.assertIn('prepareLocalSingBox(session, serverID: serverID,', DIRECTORY)
        self.assertIn('directory.prepareFullTUNCandidate(session, serverID: serverID,', DASHBOARD)
        self.assertIn('startFullTun(session, serverID: serverID, protocolCode: selectedProtocol)', DASHBOARD)

    def test_anytls_shares_safe_darwin_utun(self):
        code = DIRECTORY[DIRECTORY.index('func prepareFullTUNCandidate('):
                         DIRECTORY.index('private func localHysteria2Config(')]
        self.assertNotIn('"interface_name": "twinconnect"', code)
        self.assertIn('"auto_route": true', code)
        self.assertIn('"auto_detect_interface": true', code)

    def test_supported_fixture_passes_exact_installed_engine(self):
        if not ENGINE.is_file():
            self.skipTest('macOS sing-box is not installed')
        cfg = {'log': {'level': 'error'},
               'inbounds': [{'type': 'tun', 'tag': 'twinconnect-tun',
                             'address': ['172.19.0.1/30'], 'auto_route': True,
                             'auto_redirect': False, 'strict_route': False,
                             'stack': 'system'}],
               'outbounds': [{'type': 'anytls', 'tag': 'proxy',
                              'server': 'example.org', 'server_port': 443,
                              'password': 'fixture-not-a-credential',
                              'tls': {'enabled': True, 'server_name': 'example.org'},
                              'idle_session_check_interval': '30s',
                              'idle_session_timeout': '30s',
                              'min_idle_session': 5,
                              'client_metadata': 'TwinConnect/1.0'}],
               'route': {'final': 'proxy', 'auto_detect_interface': True}}
        run = subprocess.run([str(ENGINE), 'check', '-c', '/dev/stdin'],
                             input=json.dumps(cfg), text=True,
                             capture_output=True, timeout=15)
        self.assertEqual(run.returncode, 0,
                         'shipped sing-box rejected checked AnyTLS TUN fixture')

    def test_known_unsupported_anytls_fields_rejected_by_engine(self):
        if not ENGINE.is_file():
            self.skipTest('macOS sing-box is not installed')
        cfg = {'log': {'level': 'error'},
               'inbounds': [{'type': 'mixed', 'tag': 'local', 'listen': '127.0.0.1',
                             'listen_port': 17089}],
               'outbounds': [{'type': 'anytls', 'tag': 'proxy', 'server': 'example.org',
                              'server_port': 443, 'password': 'fixture-only',
                              'tls': {'enabled': True, 'server_name': 'example.org'},
                              'disable_reuse': False}],
               'route': {'final': 'proxy'}}
        run = subprocess.run([str(ENGINE), 'check', '-c', '/dev/stdin'],
                             input=json.dumps(cfg), text=True,
                             capture_output=True, timeout=15)
        self.assertNotEqual(run.returncode, 0)


if __name__ == '__main__':
    unittest.main()