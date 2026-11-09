"""Updater dispatch must surface systemd errors instead of ignoring them.

All tests mock subprocess, never contact systemd or restart services.
"""
from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "twinpanel_public_updater.py"
SPEC = importlib.util.spec_from_file_location("tp_updater_restart_dispatch_test", SOURCE)
assert SPEC is not None and SPEC.loader is not None
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)

CORE = ["twinpanel-api.service", "twinpanel-web.service"]


def success(args, **kwargs):
    return subprocess.CompletedProcess(args, 0, "", "")


class RestartDispatchTests(unittest.TestCase):
    def test_success_keeps_single_nonblocking_restart(self):
        with patch.object(core, "existing_units", return_value=CORE), \
             patch.object(core.subprocess, "run", side_effect=success) as run:
            core.restart_services()
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0], ["systemctl", "daemon-reload"])
        self.assertEqual(run.call_args_list[1].args[0],
                         ["systemctl", "--no-block", "restart", *CORE])
        self.assertTrue(all(call.kwargs.get("check") is True for call in run.call_args_list))

    def test_daemon_reload_failure_prevents_restart(self):
        def fail_reload(args, **kwargs):
            raise subprocess.CalledProcessError(1, args)
        with patch.object(core, "existing_units", return_value=CORE) as units, \
             patch.object(core.subprocess, "run", side_effect=fail_reload) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                core.restart_services()
        run.assert_called_once()
        units.assert_not_called()

    def test_missing_required_units_prevents_dispatch(self):
        for units in ([], ["twinpanel-web.service"], ["twinpanel-api.service"]):
            with self.subTest(units=units), \
                 patch.object(core, "existing_units", return_value=units), \
                 patch.object(core.subprocess, "run", side_effect=success) as run:
                with self.assertRaisesRegex(RuntimeError,
                                             "UPDATER_REQUIRED_SERVICE_UNIT_MISSING"):
                    core.restart_services()
                run.assert_called_once()

    def test_rejected_restart_propagates_to_updater_rollback(self):
        seen = []
        def reject_restart(args, **kwargs):
            seen.append(args)
            if "--no-block" in args:
                raise subprocess.CalledProcessError(5, args)
            return success(args)
        with patch.object(core, "existing_units", return_value=CORE), \
             patch.object(core.subprocess, "run", side_effect=reject_restart):
            with self.assertRaises(subprocess.CalledProcessError):
                core.restart_services()
        self.assertEqual(len(seen), 2)

    def test_optional_service_absence_does_not_block_core_restart(self):
        with patch.object(core, "existing_units", return_value=CORE), \
             patch.object(core.subprocess, "run", side_effect=success):
            core.restart_services()


if __name__ == "__main__":
    unittest.main()
