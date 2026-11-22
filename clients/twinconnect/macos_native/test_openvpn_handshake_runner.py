"""Offline tests for the bounded macOS OpenVPN handshake probe."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tool/test_macos_openvpn_handshake.py"
sys.path.insert(0, str(ROOT / "macos_native"))
spec = importlib.util.spec_from_file_location("handshake_probe", TOOL)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

SAFE = b"""client
dev tun
proto udp
remote vpn.example.com 1194
remote-cert-tls server
auth SHA256
redirect-gateway def1
mssfix 1300
tun-mtu 1500
resolv-retry infinite
verb 3
<ca>
-----BEGIN CERTIFICATE-----
PARSER_ONLY
-----END CERTIFICATE-----
</ca>
"""

class HandshakeRunnerTests(unittest.TestCase):
    def test_reconstructs_private_profile_without_default_route(self):
        generated = probe.sanitize_profile(SAFE).decode()
        self.assertIn("remote vpn.example.com 1194", generated)
        self.assertIn("<ca>", generated)
        self.assertNotIn("redirect-gateway", generated)
        self.assertIn("mssfix 1300", generated)

    def test_rejects_injected_hooks(self):
        with self.assertRaisesRegex(ValueError, "OVPN_UNSAFE_DIRECTIVE"):
            probe.sanitize_profile(SAFE + b"up /tmp/evil.sh\n")

    def test_does_not_disclose_log_lines(self):
        output = probe.report(
            b"remote 8.8.8.8 USERNAME=topsecret\nAUTH_FAILED", 1)
        self.assertEqual(output, "OPENVPN_AUTH_FAILED")

    def test_timeout_and_route_checks_and_teardown_are_present(self):
        src = TOOL.read_text()
        self.assertIn('"--route-nopull"', src)
        self.assertIn('"--script-security", "1"', src)
        self.assertIn('MAX_SECONDS = 35', src)
        self.assertIn('stop_group(child)', src)
        self.assertIn('current_default_route() != before', src)
        self.assertIn('DEFAULT_ROUTE_UNCHANGED', src)
        self.assertNotIn('subprocess.run(command, shell=True', src)


if __name__ == "__main__":
    unittest.main()
