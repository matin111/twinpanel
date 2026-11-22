"""Offline contract tests for OpenVPN client-to-root-helper integration.

No networking, root escalation, or OpenVPN connections in this suite.
"""
from pathlib import Path
import sys
import unittest
from unittest import mock

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
import unsigned_tun_daemon as daemon
from openvpn_profile_review import review

SWIFT = (DIR / "TwinConnectMacOSNativeDashboard.swift").read_text()
DIRECTORY = (DIR / "TwinConnectMacOSNativeDirectory.swift").read_text()
INSTALLER = (DIR.parent / "tool/install_macos_local_tun.sh").read_text()


class NativeOpenVPNIntegrationTests(unittest.TestCase):
    def test_panel_request_is_protocol_bound(self):
        self.assertIn('payload: ["protocol": "openvpn"]', DIRECTORY)
        self.assertIn('func prepareOpenVPNProfile(', DIRECTORY)
        self.assertIn('self.validEnvelope(response, session.namespace)', DIRECTORY)
        self.assertIn('candidates.count == 1', DIRECTORY)

    def test_connect_and_disconnect_use_shared_root_control(self):
        self.assertIn('if activeProtocol == "openvpn" {', SWIFT)
        self.assertIn('startOpenVPN(session, serverID: serverID)', SWIFT)
        self.assertIn('self.runFullTunClient("start", profile: envelope)', SWIFT)
        self.assertIn('self.runFullTunClient("stop")', SWIFT)
        self.assertIn('reviewOpenVPNProfile(profile)', SWIFT)

    def test_rejects_missing_openvpn_privileged_helper(self):
        profile = {"mode": "openvpn", "profile": "client\n"}
        with mock.patch.object(daemon, "trusted_root_file", return_value=False), \
             mock.patch.object(daemon.os, "open") as file_write, \
             mock.patch.object(daemon.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(ValueError, "TRUSTED_OPENVPN_NOT_INSTALLED"):
                daemon.Session().start(501, profile)
            spawn.assert_not_called()
            file_write.assert_not_called()

    def test_rejects_openvpn_injected_commands_before_file_write(self):
        malicious = ("client\ndev tun\nremote vpn.example.com 1194\n"
                     "remote-cert-tls server\nup /bin/sh\n<ca>\nCERT\n</ca>\n")
        with mock.patch.object(daemon, "trusted_root_file", return_value=True), \
             mock.patch.object(daemon.os, "access", return_value=True), \
             mock.patch.object(daemon.os, "open") as file_write:
            with self.assertRaisesRegex(ValueError, "OVPN_UNSAFE_DIRECTIVE"):
                daemon.Session().start(501, {"mode": "openvpn", "profile": malicious})
            file_write.assert_not_called()

    def test_reviewed_profile_still_never_claims_verified_vpn(self):
        self.assertIn('"system_vpn_verified": False',
                      (DIR / "unsigned_tun_daemon.py").read_text())
        self.assertIn('OPENVPN_CERTIFICATE_ROLE_REQUIRED',
                      (DIR / "unsigned_tun_daemon.py").read_text())
        self.assertIn('OPENVPN_LOCAL_HELPER_STAGED', INSTALLER)
        self.assertIn('OPENVPN_PRIVILEGED_INSTALL_CANDIDATE_PREPARED',
                      (DIR.parent / "tool/package_macos_local_proxy_runtime.sh").read_text())


if __name__ == "__main__":
    unittest.main()
