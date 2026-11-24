"""Offline installer contract checks. Never run privileged commands."""
from pathlib import Path
import re
import unittest

SCRIPT = (Path(__file__).resolve().parents[1] /
          "tool/install_macos_local_tun.sh").read_text()


class LocalInstallerContractTests(unittest.TestCase):
    def test_requires_explicit_action(self):
        self.assertIn('case "$action" in check|stage|stage-vps|activate|stop|remove)', SCRIPT)

    def test_refuses_ssh_and_remote_vps_marker(self):
        self.assertIn("SSH_CONNECTION", SCRIPT)
        self.assertIn("TWINCONNECT_REMOTE_VPS", SCRIPT)
        self.assertIn("REMOTE_SESSION_REFUSED", SCRIPT)

    def test_requires_active_console_owner(self):
        self.assertIn("SUDO_CONSOLE_USER_REQUIRED", SCRIPT)
        self.assertIn('stat -f \'%Su\' /dev/console', SCRIPT)
        self.assertIn("CONSOLE_USER_MISMATCH", SCRIPT)

    def test_requires_staging_before_activation(self):
        self.assertIn("STAGE_BEFORE_ACTIVATE", SCRIPT)
        self.assertIn('if [[ "$action" == "stage" || "$action" == "stage-vps" ]]; then', SCRIPT)
        self.assertIn("STAGE-VPS-FILES-ONLY", SCRIPT)
        self.assertLess(SCRIPT.index("LOCAL_TUN_FILES_STAGED; SERVICE_NOT_STARTED"), SCRIPT.index("launchctl bootstrap system"))
        self.assertIn("LOCAL_TUN_FILES_STAGED; SERVICE_NOT_STARTED", SCRIPT)

    def test_no_route_dns_commands(self):
        self.assertNotIn("/sbin/route ", SCRIPT)
        self.assertNotIn("networksetup -setdnsservers", SCRIPT)
        self.assertNotIn("scutil --set", SCRIPT)

    def test_manual_activation_and_shutdown(self):
        self.assertIn("LOCAL-PHYSICAL-MAC", SCRIPT)
        self.assertIn("launchctl bootstrap system", SCRIPT)
        self.assertIn("launchctl bootout system", SCRIPT)

    def test_no_automatic_tunnel_at_boot(self):
        self.assertIn("<key>KeepAlive</key><false/>", SCRIPT)
        self.assertIn("LOCAL_TUN_DAEMON_ACTIVATED; ENGINE_NOT_STARTED", SCRIPT)


if __name__ == "__main__":
    unittest.main()
