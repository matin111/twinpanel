"""Offline app-button OpenVPN integration tests; no root commands run."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = (ROOT / "macos_native/TwinConnectMacOSNativeDashboard.swift").read_text()
INSTALLER = (ROOT / "tool/install_macos_openvpn_app_probe.sh").read_text()
HANDSHAKE = (ROOT / "tool/test_macos_openvpn_handshake.py").read_text()


class OpenVPNAppButtonTests(unittest.TestCase):
    def test_main_button_selects_real_handshake_probe(self):
        action = DASHBOARD.split("@objc private func requestVPNConnection(", 1)[1]
        self.assertIn('if activeProtocol == "openvpn" {', action)
        self.assertIn('startOpenVPNAppProbe(session, serverID: serverID)', action)
        self.assertIn('if fullTunServicePresent()', action)

    def test_probe_uses_authenticated_panel_profile_and_private_stdin(self):
        section = DASHBOARD.split("private func startOpenVPNAppProbe(", 1)[1]
        self.assertIn("directory.prepareOpenVPNProfile(session, serverID: serverID)", section)
        self.assertIn("reviewOpenVPNProfile(profile)", section)
        self.assertIn('task.arguments = ["-n", "/usr/bin/python3",', section)
        self.assertIn('helper, "--stdin"]', section)
        self.assertIn("input.fileHandleForWriting.write(profile)", section)
        self.assertIn("task.standardError = FileHandle.nullDevice", section)
        self.assertIn("self.fullTunActive = false", section)
        self.assertIn("System VPN not connected.", section)

    def test_root_probe_uses_fixed_path_and_bounded_runtime(self):
        self.assertIn("/Library/PrivilegedHelperTools/TwinConnectOpenVPN", INSTALLER)
        self.assertIn("NOPASSWD: /usr/bin/python3 %s --stdin", INSTALLER)
        self.assertIn("ENABLE-OPENVPN-APP-TEST", INSTALLER)
        self.assertIn("/usr/sbin/visudo -c -f", INSTALLER)
        self.assertIn("MAX_SECONDS = 35", HANDSHAKE)
        self.assertIn('"--route-nopull"', HANDSHAKE)
        self.assertIn('target.add_argument("--stdin"', HANDSHAKE)
        self.assertIn("stop_group(child)", HANDSHAKE)
        ast.parse(HANDSHAKE)


if __name__ == "__main__":
    unittest.main()
