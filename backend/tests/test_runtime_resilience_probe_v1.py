from __future__ import annotations

import ast
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/twinpanel_runtime_resilience_probe_v1.py"
spec = importlib.util.spec_from_file_location("resilience_probe", PATH)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class RuntimeResilienceProbe(unittest.TestCase):
    def test_probe_is_read_only_and_uses_active_bluegreen_slot(self):
        source = PATH.read_text()
        ast.parse(source)
        self.assertIn("active_port", source)
        self.assertIn("idle in transaction", source)
        self.assertIn("interval '60 seconds'", source)
        for forbidden in ("systemctl restart", "ALTER DATABASE", "DELETE FROM",
                          "DROP TABLE", "kill -", "UPDATE quota"):
            self.assertNotIn(forbidden, source)

    def test_good_3001_install_with_no_stale_transactions(self):
        with tempfile.TemporaryDirectory() as d:
            current = Path(d) / "current"
            current.mkdir()
            (current / "VERSION").write_text("1.1.0-rc.766")
            state = Path(d) / "state.json"
            state.write_text(json.dumps({
                "active_port": 3001, "release": str(current.resolve()),
            }))
            def fake_run(*args, **kwargs):
                if args[0] == "systemctl":
                    return 0, "active"
                if args[0] == "nginx":
                    return 0, ""
                if args[0] == "runuser":
                    return 0, "0|0"
                raise AssertionError(args)
            with mock.patch.object(probe, "CURRENT", current), \
                 mock.patch.object(probe, "SLOT_STATE", state), \
                 mock.patch.object(probe, "run", side_effect=fake_run), \
                 mock.patch.object(probe, "http_version", return_value="1.1.0-rc.766"):
                result = probe.report()
            self.assertTrue(result["healthy"], result["errors"])
            self.assertEqual(result["active_web_port"], 3001)

    def test_3000_is_owned_by_pinned_slot_after_bluegreen_cutover(self):
        with tempfile.TemporaryDirectory() as d:
            current = Path(d) / "current"
            current.mkdir()
            (current / "VERSION").write_text("1.1.0-rc.767")
            state = Path(d) / "state.json"
            state.write_text(json.dumps({
                "active_port": 3000, "release": str(current.resolve()),
            }))
            def fake_run(*args, **kwargs):
                if args[0] == "systemctl":
                    if args[-1] == "twinpanel-web.service":
                        return 3, "inactive"
                    return 0, "active"
                if args[0] == "runuser":
                    return 0, "0|0"
                return 0, ""
            with mock.patch.object(probe, "CURRENT", current), \
                 mock.patch.object(probe, "SLOT_STATE", state), \
                 mock.patch.object(probe, "run", side_effect=fake_run), \
                 mock.patch.object(probe, "http_version", return_value="1.1.0-rc.767"):
                result = probe.report()
            self.assertTrue(result["healthy"], result["errors"])
            self.assertEqual(result["service_status"]["active_web_unit"],
                             "twinpanel-web-slot@3000.service")

    def test_stale_database_transaction_is_visible_not_mutated(self):
        with tempfile.TemporaryDirectory() as d:
            current = Path(d)/"current"
            current.mkdir()
            (current/"VERSION").write_text("1.1.0-rc.766")
            state = Path(d)/"state.json"
            state.write_text(json.dumps({
                "active_port": 3001, "release": str(current.resolve()),
            }))
            def fake_run(*args, **kwargs):
                if args[0] == "runuser":
                    return 0, "2|90"
                return 0, "active"
            with mock.patch.object(probe, "CURRENT", current), \
                 mock.patch.object(probe, "SLOT_STATE", state), \
                 mock.patch.object(probe, "run", side_effect=fake_run), \
                 mock.patch.object(probe, "http_version", return_value="1.1.0-rc.766"):
                result = probe.report()
            self.assertFalse(result["healthy"])
            self.assertEqual(result["stale_db_transactions"], 2)
            self.assertIn("idle_postgres_transactions_over_60s", result["errors"])

    def test_updater_installs_timer_only_after_success_gate(self):
        updater = (ROOT / "scripts/twinpanel_public_updater.py").read_text()
        ast.parse(updater)
        self.assertIn("install_resilience_probe_timer(final)", updater)
        self.assertIn("UPDATER_RESILIENCE_PROBE_INSTALL_WARNING", updater)
        self.assertIn("systemctl\", \"enable\", \"--now\", \"twinpanel-resilience-probe.timer", updater)
        self.assertLess(updater.index("install_node_auto_backfill_timer(final)"),
                        updater.index("install_resilience_probe_timer(final)"))


if __name__ == "__main__":
    unittest.main()
