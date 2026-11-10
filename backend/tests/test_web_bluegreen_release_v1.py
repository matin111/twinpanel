"""Isolated blue/green Web routing regression (never touches live Nginx)."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

FILE = Path(__file__).resolve().parents[1] / "scripts" / "twinpanel_web_bluegreen_v1.py"
spec = importlib.util.spec_from_file_location("bluegreen", FILE)
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)


class WebSlots(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        enabled = root / "enabled"
        enabled.mkdir()
        sites = root / "available"
        sites.mkdir()
        self.site = sites / "panel.conf"
        self.site.write_text("location / { proxy_pass http://127.0.0.1:3000; }\\nlocation /_next/static/ { proxy_pass http://127.0.0.1:3000; }\\n", encoding="utf-8")
        (enabled / "panel.conf").symlink_to(self.site)
        self.state = root / "state.json"
        self.patcher = mock.patch.multiple(
            web, ENABLED=enabled, STATE=self.state,
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.original = self.site.read_text()

    def test_cutover_only_after_nginx_test_and_reload(self):
        actions = []
        def command(*args, **_kwargs):
            actions.append(args)
        with mock.patch.object(web, "cmd", side_effect=command), mock.patch.object(
            web, "versioned_release", side_effect=lambda p: p
        ), mock.patch.object(web, "nginx_targets", return_value=[self.site]):
            web.activate(3000, 3001, Path("/opt/twinpanel/releases/1.1.0-rc.999"))
            self.assertIn("127.0.0.1:3001;", self.site.read_text())
            self.assertNotIn("127.0.0.1:3000;", self.site.read_text())
            self.assertEqual(actions[:2], [("nginx", "-t"), ("systemctl", "reload", "nginx")])
            self.assertEqual(json.loads(self.state.read_text())["active_port"], 3001)
            web.revert(3000, 3001, Path("/opt/twinpanel/releases/1.1.0-rc.998"))
            self.assertEqual(self.site.read_text(), self.original)

    def test_bad_nginx_rolls_files_back_before_exiting(self):
        calls = []
        def command(*args, **_kwargs):
            calls.append(args)
            if args == ("nginx", "-t") and len(calls) == 1:
                raise subprocess.CalledProcessError(1, args)
        with mock.patch.object(web, "nginx_targets", return_value=[self.site]), mock.patch.object(web, "cmd", side_effect=command):
            with self.assertRaises(subprocess.CalledProcessError):
                web._update_nginx(3000, 3001)
        self.assertEqual(self.site.read_text(), self.original)
        self.assertFalse(self.state.exists())

    def test_refuses_ambiguous_or_unrecognized_frontends(self):
        self.site.write_text(self.original + "proxy_pass http://127.0.0.1:3001;\\n")
        with mock.patch.object(web, "nginx_targets", return_value=[self.site]):
            with self.assertRaisesRegex(RuntimeError, "MULTIPLE"):
                web.old_port()

    def test_web_unit_has_no_global_prestart_side_effects(self):
        self.assertNotIn("ExecStartPre", web.UNIT)
        self.assertIn('TP_WEB_RELEASE', web.UNIT)
        self.assertIn("SuccessExitStatus=143", web.UNIT)
        self.assertNotIn("/opt/twinpanel/current/.next", web.UNIT)

    def test_partial_candidate_start_cleans_standby_without_touching_active(self):
        with mock.patch.object(web, "old_port", return_value=3000), \
             mock.patch.object(web, "versioned_release", side_effect=lambda p: p), \
             mock.patch.object(web, "copy_previous_static"), \
             mock.patch.object(web, "SLOT_UNIT", Path(self.tmp.name) / "slot.service"), \
             mock.patch.object(web, "ENV_DIR", Path(self.tmp.name)), \
             mock.patch.object(web.subprocess, "run", return_value=mock.Mock(returncode=1)) as runner:
            calls = []
            def command(*args, **kwargs):
                calls.append(args)
                if args[:2] == ("systemctl", "enable"):
                    raise RuntimeError("enable_failed")
            with mock.patch.object(web, "cmd", side_effect=command):
                with self.assertRaisesRegex(RuntimeError, "enable_failed"):
                    web.prepare(Path("/opt/twinpanel/releases/1.1.0-rc.768"),
                                Path("/opt/twinpanel/releases/1.1.0-rc.767"))
            self.assertIn(("systemctl", "start", "twinpanel-web-slot@3001.service"), calls)
            runner.assert_any_call(
                ["systemctl", "disable", "--now", "twinpanel-web-slot@3001.service"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False, timeout=25,
            )
            self.assertNotIn(("systemctl", "stop", "twinpanel-web-slot@3000.service"), calls)


    def test_reboot_persistence_and_safe_retire(self):
        source = FILE.read_text()
        self.assertIn('cmd("systemctl", "enable", unit)', source)
        self.assertIn('cmd("systemctl", "disable", "--now", "twinpanel-web.service")', source)
        self.assertIn('cmd("systemctl", "disable", "--now", f"twinpanel-web-slot@{old}.service")', source)

    def test_legacy_prestart_migrations_are_preserved(self):
        updater = (FILE.parent / "twinpanel_public_updater.py").read_text()
        for helper in (
            "twinpanel_nginx_reconcile.py",
            "twinpanel_updater_unit_reconcile_v69.py",
            "twinpanel_api_update_handoff_v69.py",
            "twinpanel_runtime_unit_reconcile.py",
            "twinpanel_accounting_unit_reconcile.py",
        ):
            self.assertIn(helper, updater)
        self.assertIn("converge_web_prestart_helpers_for_bluegreen(final, env)", updater)


    def test_updater_never_restarts_legacy_web_when_bluegreen_enabled(self):
        updater = (FILE.parent / "twinpanel_public_updater.py").read_text()
        self.assertIn("restart_services(include_web=bg is None)", updater)
        self.assertIn("bg.activate(bg_ports[0], bg_ports[1], final)", updater)
        self.assertIn("bg.revert(bg_ports[0], bg_ports[1], previous)", updater)
        self.assertIn("bg.stop_unused(bg_ports[0])", updater)


if __name__ == "__main__":
    unittest.main()
