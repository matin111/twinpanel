"""Offline watchdog tests; no privilege, routing, or process termination."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock

DIR = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "unsigned_tun_watchdog", DIR / "unsigned_tun_watchdog.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class WatchdogTests(unittest.TestCase):
    def test_invalid_process_ids_rejected(self):
        for value in (-1, 0, 1, 2**23):
            self.assertFalse(module.valid_pid(value))

    def test_refuses_non_root_and_other_platforms(self):
        with mock.patch.object(module.sys, "platform", "linux"), \
             mock.patch.object(module.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(ValueError, "LOCAL_ROOT_MAC_REQUIRED"):
                module.watch(100, 200, 60)

    def test_refuses_parent_pid_mismatch(self):
        with mock.patch.object(module.sys, "platform", "darwin"), \
             mock.patch.object(module.os, "geteuid", return_value=0), \
             mock.patch.object(module.os, "getppid", return_value=101):
            with self.assertRaisesRegex(ValueError, "WATCHDOG_NOT_CHILD_OF_DAEMON"):
                module.watch(100, 200, 60)

    def test_refuses_excessive_watchdog_duration(self):
        with self.assertRaisesRegex(ValueError, "INVALID_WATCHDOG_DURATION"):
            module.watch(100, 200, module.MAX_SECONDS + 1)

    def test_terminate_only_owned_process_group(self):
        with mock.patch.object(module.os, "getpgid", return_value=999), \
             mock.patch.object(module.os, "killpg") as kill:
            module.terminate_group(200)
            kill.assert_not_called()
        with mock.patch.object(module.os, "getpgid", return_value=200), \
             mock.patch.object(module.os, "killpg") as kill:
            module.terminate_group(200)
            kill.assert_called_once_with(200, module.signal.SIGTERM)

    def test_parent_death_watchdog_linked_into_daemon(self):
        daemon = (DIR / "unsigned_tun_daemon.py").read_text()
        installer = (DIR.parent / "tool/install_macos_local_tun.sh").read_text()
        self.assertIn('WATCHDOG = TRUSTED_ROOT / "unsigned_tun_watchdog.py"', daemon)
        self.assertIn("TUN_WATCHDOG_START_FAILED", daemon)
        self.assertIn("WATCHDOG_READY", daemon)
        self.assertIn("unsigned_tun_watchdog.py", installer)


if __name__ == "__main__":
    unittest.main()
