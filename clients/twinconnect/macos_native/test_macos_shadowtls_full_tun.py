"""ShadowTLS v3 + Shadowsocks detour on macOS unsigned TUN, offline only."""
from pathlib import Path
import json
import subprocess
import unittest

ROOT = Path(__file__).parent
SOURCE = (ROOT / "TwinConnectMacOSNativeDirectory.swift").read_text()
UI = (ROOT / "TwinConnectMacOSNativeDashboard.swift").read_text()
ENGINE = ROOT / "build/singbox/amd64/sing-box"


class ShadowTLSTunTests(unittest.TestCase):
    def test_shadowtls_review_preserves_two_distinct_outbounds(self):
        code = SOURCE[SOURCE.index('private func reviewedShadowTLSProxyConfig('):
                      SOURCE.index('private func safeProxyRemoteHost(', SOURCE.index(
                          'private func reviewedShadowTLSProxyConfig('))]
        self.assertIn('rows.count == 2', code)
        self.assertIn('ss["detour"] as? String == tag', code)
        self.assertIn('transport["version"] as? Int == 3', code)
        self.assertIn('"type": "shadowsocks", "tag": "proxy"', code)
        self.assertIn('"type": "shadowtls", "tag": "shadowtls-transport"', code)
        self.assertIn('inner["udp_over_tcp"] = ["enabled": true, "version": 2]', code)
        self.assertIn('trustedTLS["insecure"] = false', code)

    def test_root_tun_rejects_shadowtls_chain_without_detour(self):
        start = SOURCE.index('func prepareFullTUNCandidate(')
        end = SOURCE.index('private func localHysteria2Config(', start)
        code = SOURCE[start:end]
        self.assertIn('if protocolCode == "shadowtls" {', code)
        self.assertIn('outbounds.count == 2', code)
        self.assertIn('first["detour"] as? String == "shadowtls-transport"', code)
        self.assertIn('outbounds[1]["version"] as? Int == 3', code)
        self.assertIn('"SHADOWTLS_CHAIN_INVALID"', code)
        self.assertIn('"auto_route": true', code)
        self.assertIn('"auto_detect_interface": true', code)
        self.assertNotIn('"interface_name": "twinconnect"', code)

    def test_ui_starts_actual_tun_not_only_local_proxy(self):
        self.assertIn('"naive", "shadowtls"', SOURCE)
        self.assertIn('directory.prepareFullTUNCandidate(session, serverID: serverID,', UI)
        self.assertIn('startFullTun(session, serverID: serverID, protocolCode: selectedProtocol)', UI)
        self.assertIn('case "shadowtls": return "ShadowTLS"', UI)

    def test_installed_singbox_accepts_two_stage_tun_config(self):
        if not ENGINE.is_file():
            self.skipTest('sing-box is not installed in this environment')
        profile = {
            "log": {"level": "error"},
            "inbounds": [{"type": "tun", "tag": "twinconnect-tun",
                "address": ["172.19.0.1/30"], "auto_route": True,
                "auto_redirect": False, "strict_route": False, "stack": "system"}],
            "outbounds": [
                {"type": "shadowsocks", "tag": "proxy", "method": "aes-256-gcm",
                 "password": "test-only", "detour": "shadowtls-transport",
                 "udp_over_tcp": {"enabled": True, "version": 2}},
                {"type": "shadowtls", "tag": "shadowtls-transport", "version": 3,
                 "server": "example.org", "server_port": 443,
                 "password": "test-only",
                 "tls": {"enabled": True, "server_name": "example.org"}}
            ],
            "route": {"final": "proxy", "auto_detect_interface": True}
        }
        res = subprocess.run([str(ENGINE), "check", "-c", "/dev/stdin"],
            input=json.dumps(profile), capture_output=True, text=True, timeout=15)
        self.assertEqual(res.returncode, 0, 'sing-box rejected offline ShadowTLS profile')


if __name__ == '__main__':
    unittest.main()