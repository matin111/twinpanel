"""Read-only checks for the VPS TUN root setup safety contract."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "tool/setup_macos_tun_limited_sudo.sh"
SCRIPT = SOURCE.read_text(encoding="utf-8")


class LimitedTunAdminSetupTests(unittest.TestCase):
    def test_root_owned_path_not_writable_usr_local_sbin(self):
        self.assertIn('/Library/PrivilegedHelperTools/TwinConnectOps', SCRIPT)
        self.assertNotIn('/usr/local/sbin/twinconnect', SCRIPT)
        self.assertIn('/usr/sbin/chown root:wheel "$ops/tun-admin"', SCRIPT)

    def test_grant_is_narrow(self):
        self.assertIn('NOPASSWD: %s status, %s stop', SCRIPT)
        self.assertNotIn('NOPASSWD: ALL', SCRIPT)
        self.assertNotIn('NOPASSWD: /bin/bash', SCRIPT)

    def test_error_codes_installer_queries_as_console_owner(self):
        script = (SOURCE.parent / "upgrade_macos_tun_error_codes.sh").read_text()
        self.assertEqual(script.count('/usr/bin/sudo -n -u "$admin" /usr/bin/python3'), 2)
        self.assertIn('/usr/bin/cmp -s "$source" "$target"', script)
        self.assertIn("CONTROLLER_ALREADY_CURRENT_AND_READY", script)
        self.assertNotIn('if /usr/bin/python3 macos_native/unsigned_tun_client.py status |', script)

    def test_error_codes_installer_waits_for_controller_readiness(self):
        script = (SOURCE.parent / "upgrade_macos_tun_error_codes.sh").read_text()
        self.assertIn("CONTROLLER_NOT_READY", script)
        self.assertIn("'\"state\": \"stopped\"'", script)
        self.assertIn("NO_VPN_STARTED", script)

    def test_vps_controller_requires_oob_and_bounded_expiry(self):
        installer = (SOURCE.parent / "activate_macos_tun_vps.sh").read_text()
        self.assertIn("PROVIDER_VNC_CONSOLE_REQUIRED", installer)
        self.assertIn("ENABLE-VPS-TUN-CONTROLLER", installer)
        self.assertIn("VPS_SESSION = 45", installer)
        self.assertIn("NO_VPN_STARTED; MAX_TRIAL_45_SECONDS", installer)
        self.assertNotIn("sing-box run", installer)
        self.assertNotIn("route add", installer)

    def test_setup_is_staging_only(self):
        self.assertIn('DAEMON_NOT_STARTED; ROUTES_UNCHANGED', SCRIPT)
        self.assertNotIn('launchctl bootstrap', SCRIPT)
        self.assertNotIn('route add', SCRIPT)
        self.assertNotIn('route change', SCRIPT)
        self.assertIn('INTERACTIVE_PROVIDER_CONSOLE_REQUIRED', SCRIPT)


if __name__ == "__main__":
    unittest.main()