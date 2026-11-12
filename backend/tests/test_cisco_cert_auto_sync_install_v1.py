"""Guard installation/update contracts for Cisco's trusted certificate sync."""
from __future__ import annotations

import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class CiscoCertificateAutoSyncInstallTest(unittest.TestCase):
    def test_safe_sync_and_unit_files_exist(self):
        script = ROOT / "backend/scripts/twinpanel_cisco_cert_pin_sync_v1.py"
        contents = script.read_text()
        ast.parse(contents, filename=str(script))
        self.assertIn("ssh_connect_saved", contents)
        self.assertIn("pin-sha256:", contents)
        self.assertIn("certificate identity CHANGED", contents)
        self.assertIn("continue", contents)
        self.assertNotIn("verify=False", contents)
        for ext in ("service", "timer"):
            unit = ROOT / f"deploy/systemd/twinpanel-cisco-pin-sync.{ext}"
            self.assertTrue(unit.is_file())

    def test_installer_enables_periodic_sync(self):
        installer = (ROOT / "installer/install.sh").read_text()
        self.assertIn("twinpanel-cisco-pin-sync.service", installer)
        self.assertIn("twinpanel-cisco-pin-sync.timer", installer)
        self.assertIn("systemctl enable --now twinpanel-cisco-pin-sync.timer", installer)

    def test_updater_restores_sync_after_release_change(self):
        updater = ROOT / "backend/scripts/twinpanel_public_updater.py"
        source = updater.read_text()
        ast.parse(source, filename=str(updater))
        self.assertIn("def install_cisco_cert_pin_timer", source)
        self.assertIn("install_cisco_cert_pin_timer(final)", source)
        self.assertIn("systemctl\", \"enable\", \"--now\", \"twinpanel-cisco-pin-sync.timer", source)

    def test_unit_runs_script_from_current_release(self):
        unit = (ROOT / "deploy/systemd/twinpanel-cisco-pin-sync.service").read_text()
        self.assertIn("/opt/twinpanel/current/backend/scripts/twinpanel_cisco_cert_pin_sync_v1.py", unit)
        self.assertIn("EnvironmentFile=/etc/twinpanel/backend.env", unit)
        timer = (ROOT / "deploy/systemd/twinpanel-cisco-pin-sync.timer").read_text()
        self.assertIn("OnUnitInactiveSec=3min", timer)


if __name__ == "__main__":
    unittest.main()
