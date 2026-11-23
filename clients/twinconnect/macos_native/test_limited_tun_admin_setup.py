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

    def test_setup_is_staging_only(self):
        self.assertIn('DAEMON_NOT_STARTED; ROUTES_UNCHANGED', SCRIPT)
        self.assertNotIn('launchctl bootstrap', SCRIPT)
        self.assertNotIn('route add', SCRIPT)
        self.assertNotIn('route change', SCRIPT)
        self.assertIn('INTERACTIVE_PROVIDER_CONSOLE_REQUIRED', SCRIPT)


if __name__ == "__main__":
    unittest.main()