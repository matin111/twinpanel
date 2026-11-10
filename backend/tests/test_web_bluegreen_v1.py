"""No-prod-I/O tests for web 3000 standby and reversible Nginx routing.

All systemd, Nginx and release data are replaced by temporary paths and mocks.
"""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from scripts import twinpanel_web_bluegreen_v1 as mod


class WebBlueGreenTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.nginx = root / "nginx"
        self.main = root / "current"
        self.releases = root / "releases"
        self.site_dir = self.nginx / "sites-available"
        self.enabled = self.nginx / "sites-enabled"
        self.site_dir.mkdir(parents=True)
        self.enabled.mkdir()
        self.releases.mkdir()
        self.main.mkdir()
        (self.main / "VERSION").write_text("1.1.0-rc.762")
        self.site_a = self.site_dir / "twinpanel"
        self.site_b = self.site_dir / "domains.conf"
        self.site_a.write_text(
            "server {\n  location / {proxy_pass http://127.0.0.1:3000;}\n"
            "  location /v1/ {proxy_pass http://127.0.0.1:8095;}\n}\n"
        )
        self.site_b.write_text(
            "server {\n  location / {proxy_pass http://127.0.0.1:3000;}\n"
            "  location /admin/ {proxy_pass http://127.0.0.1:3000;}\n}\n"
        )
        (self.enabled / "twinpanel").symlink_to(self.site_a)
        (self.enabled / "domains.conf").symlink_to(self.site_b)
        self.state = root / "license" / "handoff.json"
        self.backup = root / "license" / "backup"
        self.patchers = [
            mock.patch.object(mod, "ROOT", self.nginx),
            mock.patch.object(mod, "STATE", self.state),
            mock.patch.object(mod, "BACKUP_ROOT", self.backup),
            mock.patch.object(mod, "CURRENT", self.main),
            mock.patch.object(mod, "RELEASE_ROOT", self.releases),
            mock.patch.object(mod, "_require_root"),
        ]
        for p in self.patchers:
            p.start()
            self.addCleanup(p.stop)

    def _staged(self):
        plan = mod.plan()
        self.backup.mkdir(parents=True)
        paths = {}
        for idx, (name, before) in enumerate(plan["originals"].items()):
            bak = f"source-{idx}.bak"
            (self.backup / bak).write_text(before)
            paths[name] = {
                "backup": bak,
                "before": mod._sha(before.encode()),
                "staged": mod._sha(plan["replacements"][name].encode()),
            }
        mod._save_json({
            "phase": "staged", "version": "1.1.0-rc.763",
            "sites": paths, "standby_port": 33001, "primary_port": 3000,
        })

    def test_plan_deduplicates_symlinks_and_preserves_api_routes(self):
        planned = mod.plan()
        self.assertEqual(planned["sites"], 2)
        self.assertEqual(planned["routes"], 3)
        self.assertIn("127.0.0.1:8095", planned["replacements"][str(self.site_a)])
        self.assertNotIn("127.0.0.1:33001", self.site_a.read_text())

    def test_rejects_mixed_or_already_switched_sites(self):
        self.site_b.write_text(self.site_b.read_text().replace(":3000", ":33001"))
        with self.assertRaisesRegex(RuntimeError, "ALREADY_SWITCHED"):
            mod.plan()
        self.assertIn(":3000", self.site_a.read_text())

    def test_switch_and_restore_are_bounded_and_lossless(self):
        self._staged()
        with mock.patch.object(mod, "_http_health", return_value=True), \
             mock.patch.object(mod, "_run") as run:
            mod.route_standby()
            self.assertIn(":33001", self.site_a.read_text())
            self.assertIn(":33001", self.site_b.read_text())
            self.assertIn(":8095", self.site_a.read_text())
            self.assertEqual(json.loads(self.state.read_text())["phase"], "serving_standby")
            mod.restore("1.1.0-rc.763")
            self.assertNotIn(":33001", self.site_a.read_text())
            self.assertNotIn(":33001", self.site_b.read_text())
            self.assertIn(":8095", self.site_a.read_text())
            self.assertFalse(self.state.exists())
            self.assertFalse(self.backup.exists())
            self.assertIn(mock.call("systemctl", "stop", mod.STANDBY_UNIT), run.call_args_list)

    def test_crash_after_nginx_reload_before_state_write_restores_safely(self):
        self._staged()
        before = json.loads(self.state.read_text())
        # Simulate an interrupted handoff after nginx reload but before
        # phase becomes serving_standby: state remains "staged".
        plan = mod.plan()
        self.site_a.write_text(plan["replacements"][str(self.site_a)])
        self.site_b.write_text(plan["replacements"][str(self.site_b)])
        self.assertEqual(before["phase"], "staged")
        with mock.patch.object(mod, "_http_health", return_value=True), \
             mock.patch.object(mod, "_run"):
            mod.restore("1.1.0-rc.762")
        self.assertIn("127.0.0.1:3000", self.site_a.read_text())
        self.assertIn("127.0.0.1:3000", self.site_b.read_text())
        self.assertFalse(self.state.exists())
        self.assertFalse(self.backup.exists())

    def test_stale_backup_directory_aborts_without_removing_evidence(self):
        self.backup.mkdir(parents=True)
        marker_path = self.backup / "orphaned.bak"
        marker_path.write_text("leave untouched")
        with mock.patch.object(mod, "_run") as run:
            with self.assertRaisesRegex(RuntimeError, "EXISTING_STATE_OR_BACKUP"):
                mod.stage(self.releases, "1.1.0-rc.763")
        self.assertTrue(marker_path.exists())
        run.assert_not_called()

    def test_detects_external_nginx_change_without_overwriting_it(self):
        self._staged()
        self.site_a.write_text(self.site_a.read_text() + "\n# external edit\n")
        with mock.patch.object(mod, "_http_health", return_value=True), \
             mock.patch.object(mod, "_run") as run:
            with self.assertRaisesRegex(RuntimeError, "CONFIG_CHANGED_EXTERNALLY"):
                mod.route_standby()
        self.assertIn("external edit", self.site_a.read_text())
        run.assert_not_called()

    def test_nginx_failure_restores_original_bytes_before_reload(self):
        self._staged()
        def system_commands(*args, **kwargs):
            if args == ("nginx", "-t"):
                raise RuntimeError("invalid test config")
        with mock.patch.object(mod, "_http_health", return_value=True), \
             mock.patch.object(mod, "_run", side_effect=system_commands):
            with self.assertRaises(RuntimeError):
                mod.route_standby()
        self.assertIn(":3000", self.site_a.read_text())
        self.assertIn(":3000", self.site_b.read_text())

    def test_prewarm_checks_release_and_does_not_rewrite_sites(self):
        new = self.releases / "1.1.0-rc.763"
        stand = new / ".next" / "standalone"
        stand.mkdir(parents=True)
        (new / "VERSION").write_text("1.1.0-rc.763")
        (stand / "server.js").write_text("// harmless dummy\n")
        fake_systemctl = mock.Mock(return_value=mock.Mock(returncode=1))
        with mock.patch.object(mod.subprocess, "run", fake_systemctl), \
             mock.patch.object(mod, "_run") as run, \
             mock.patch.object(mod, "_http_health", return_value=True):
            report = mod.stage(new, "1.1.0-rc.763")
        self.assertEqual(report["sites"], 2)
        self.assertTrue(self.state.exists())
        self.assertIn(":3000", self.site_a.read_text())
        self.assertIn("systemd-run", run.call_args.args)
        with mock.patch.object(mod, "_run"), \
             mock.patch.object(mod, "_http_health", return_value=True):
            mod.restore("1.1.0-rc.762")

    def test_staging_invalid_artifact_does_not_spawn_service(self):
        bad = self.releases / "invalid"
        bad.mkdir()
        (bad / "VERSION").write_text("1.1.0-rc.763")
        with mock.patch.object(mod, "_run") as run:
            with self.assertRaisesRegex(RuntimeError, "STANDALONE_MISSING"):
                mod.stage(bad, "1.1.0-rc.763")
        run.assert_not_called()
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    import unittest
    unittest.main()
