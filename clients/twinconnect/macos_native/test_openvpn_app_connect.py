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

    def test_openvpn_progress_and_errors_are_available_in_connect_tooltip(self):
        section = DASHBOARD.split("private func connectPage()", 1)[1]
        section = section.split("private func ", 1)[0]
        self.assertIn('let openVPNHasDiagnostic = activeProtocol == "openvpn"', section)
        self.assertIn('connect.toolTip =', section)
        self.assertIn('activeProtocol == "openvpn" && openVPNHasDiagnostic ? status', section)

    def test_result_parser_ignores_stop_marker_and_prioritizes_handshake(self):
        section = DASHBOARD.split("private func startOpenVPNAppProbe(", 1)[1]
        section = section.split("private func startOpenVPN(", 1)[0]
        self.assertIn('$0 != "OPENVPN_TEST_STOPPED"', section)
        self.assertIn('$0 == "OPENVPN_HANDSHAKE_VERIFIED"', section)
        self.assertIn('summary = outcomes.first(where:', section)
        self.assertIn('self.fullTunActive = false', section)

    def test_persistent_start_stop_from_real_connect_button(self):
        section = DASHBOARD.split("@objc private func requestVPNConnection(", 1)[1]
        self.assertIn("if openVPNAppSessionActive {", section)
        self.assertIn("stopPersistentOpenVPN()", section)
        self.assertIn("if openVPNAppSessionInstalled() {", section)
        self.assertIn("startPersistentOpenVPN(session, serverID: serverID)", section)
        self.assertIn("refreshOpenVPNAppSession()", DASHBOARD)
        self.assertIn("OpenVPN tunnel only · not system VPN", DASHBOARD)

    def test_persistent_script_has_route_guard_and_auto_expiry(self):
        script = (ROOT / "macos_native/openvpn_app_session.py").read_text()
        self.assertIn("MAX_SESSION_SECONDS = 86400", script)
        self.assertIn("deadline = time.time() + MAX_SESSION_SECONDS", script)
        self.assertIn("while time.time() < deadline and not STOP.exists()", script)
        self.assertIn('"--route-nopull"', script)
        self.assertIn("default_route() != before", script)
        self.assertIn("stop_openvpn(child)", script)
        self.assertIn("os.O_NOFOLLOW", script)
        self.assertIn('sys.argv[1] not in (', script)
        ast.parse(script)

    def test_https_egress_probe_is_bound_only_to_openvpn_utun(self):
        script = (ROOT / "macos_native/openvpn_app_session.py").read_text()
        self.assertIn('"/usr/bin/curl", "--interface", "if!" + interface', script)
        self.assertIn('added = sorted(utun_interfaces() - before_utun)', script)
        self.assertIn("len(added) == 1", script)
        self.assertIn("tunnel_egress_verified_unrouted", script)
        self.assertIn('default_route() != before', script)
        self.assertIn('"--route-nopull"', script)
        self.assertIn("system_vpn_verified", script)
        self.assertIn("OpenVPN tunnel only; system routing not active.", DASHBOARD)
        ast.parse(script)

    def test_sudoers_rule_uses_separate_fixed_action_commands(self):
        self.assertIn("upgrade)", INSTALLER)
        self.assertIn("APP_OPENVPN_SESSION_INSTALLED", INSTALLER)
        self.assertIn(" %s start", INSTALLER)
        self.assertIn(" %s stop", INSTALLER)
        self.assertIn(" %s status", INSTALLER)

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
