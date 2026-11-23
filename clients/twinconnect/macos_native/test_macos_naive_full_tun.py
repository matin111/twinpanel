"""NaiveProxy on macOS: real tenant-CA TLS, native sing-box, and full TUN."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).parent
DIRECTORY = (ROOT / 'TwinConnectMacOSNativeDirectory.swift').read_text()
UI = (ROOT / 'TwinConnectMacOSNativeDashboard.swift').read_text()
ENGINE = ROOT / 'build/singbox/amd64/sing-box'


class NaiveFullTUNTests(unittest.TestCase):
    def test_naive_profile_requires_custom_tls_trust(self):
        code = DIRECTORY[
            DIRECTORY.index('} else if protocolCode == "naive" {'):
            DIRECTORY.index('} else {\n            guard let password = outbound', DIRECTORY.index('} else if protocolCode == "naive" {'))]
        self.assertIn('let authority = checkedTLS["certificate"] as? [String]', code)
        self.assertIn('!authority.isEmpty', code)
        self.assertIn('"enabled": true', code)
        self.assertIn('"server_name": sni, "certificate": authority', code)
        self.assertIn('outbound["extra_headers"] == nil', code)
        self.assertIn('reviewed["insecure_concurrency"] = 0', code)
        self.assertIn('if outbound["quic"] as? Bool == true', code)

    def test_final_tun_preflight_only_accepts_complete_naive(self):
        code = DIRECTORY[DIRECTORY.index('func prepareFullTUNCandidate('):
                         DIRECTORY.index('private func localHysteria2Config(')]
        self.assertIn('if protocolCode == "naive" {', code)
        self.assertIn('outbounds.count == 1', code)
        self.assertIn('first["type"] as? String == "naive"', code)
        self.assertIn('first["username"] as? String', code)
        self.assertIn('tls["enabled"] as? Bool == true', code)
        self.assertIn('tls["insecure"] as? Bool != true', code)
        self.assertIn('first["insecure_concurrency"] as? Int == 0', code)
        self.assertIn('"NAIVE_TUN_PROFILE_INVALID"', code)
        self.assertIn('"auto_route": true', code)
        self.assertIn('"auto_detect_interface": true', code)
        self.assertNotIn('"interface_name": "twinconnect"', code)

    def test_connection_shows_actual_naiveproxy_label(self):
        self.assertEqual(UI.count('case "naive": return "NaiveProxy"'), 2)
        self.assertIn('startFullTun(session, serverID: serverID, protocolCode: selectedProtocol)', UI)
        self.assertIn('directory.prepareFullTUNCandidate(session, serverID: serverID,', UI)
        self.assertIn('fullTunConnectedProtocol = self.fullTunActive ?', UI)

    def test_installed_singbox_accepts_trusted_naive_tun(self):
        if not ENGINE.is_file():
            self.skipTest("Naive-enabled sing-box is not installed")
        with tempfile.TemporaryDirectory() as temp:
            cert = Path(temp)/"test-ca.pem"
            key = Path(temp)/"test-key.pem"
            proc = subprocess.run(
                ['/usr/bin/openssl', 'req', '-new', '-newkey', 'rsa:2048',
                 '-x509', '-days', '1', '-nodes', '-keyout', str(key),
                 '-out', str(cert), '-subj', '/CN=example.org'],
                capture_output=True, timeout=18)
            self.assertEqual(proc.returncode, 0,
                             'could not build local-only synthetic TLS fixture')
            config = {
                'log': {'level': 'error'},
                'inbounds': [{'type': 'tun', 'tag': 'twinconnect-tun',
                    'address': ['172.19.0.1/30'], 'auto_route': True,
                    'auto_redirect': False, 'strict_route': False,
                    'stack': 'system'}],
                'outbounds': [{'type': 'naive', 'tag': 'proxy',
                    'server': 'example.org', 'server_port': 443,
                    'username': 'fixture-user', 'password': 'fixture-only',
                    'tls': {'enabled': True, 'server_name': 'example.org',
                            'certificate': [cert.read_text()]},
                    'insecure_concurrency': 0}],
                'route': {'final': 'proxy', 'auto_detect_interface': True}}
            checked = subprocess.run(
                [str(ENGINE), 'check', '-c', '/dev/stdin'],
                input=json.dumps(config), capture_output=True, text=True,
                timeout=18)
            self.assertEqual(checked.returncode, 0,
                             'installed sing-box rejected TLS-verified Naive TUN')


if __name__ == '__main__':
    unittest.main()