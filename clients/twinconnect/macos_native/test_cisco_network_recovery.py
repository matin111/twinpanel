"""Offline macOS Cisco network recovery regression checks.

All subprocesses, root operations and networking are mocked. Never changes
host IP, DNS, routes or network services.
"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "cisco_network_recovery", HERE / "cisco_network_recovery.py")
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)

STATIC = {"version": 1, "interface": "en0", "service": "Ethernet",
          "mode": "manual", "ip": "198.51.100.36",
          "mask": "255.255.255.240", "gateway": "198.51.100.33",
          "dns": ["198.51.100.19"]}


class CiscoRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(
            recovery, "CHECKPOINT", Path(self.tmp.name) / "checkpoint.json")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_readiness_rejects_console_management_without_network_changes(self):
        with mock.patch.object(recovery, "capture", return_value=STATIC), \
             mock.patch.object(recovery, "command") as cmd, \
             mock.patch.object(recovery, "BASE", Path(self.tmp.name)):
            (Path(self.tmp.name) / "management_ipv4").write_text(
                "console-test\n")
            result = recovery.readiness()
            self.assertEqual(result["state"], "CISCO_PRECHECK_BLOCKED")
            self.assertIn("CISCO_REMOTE_MANAGEMENT_NOT_PINNED",
                          result["reasons"])
            self.assertFalse(result["vpn_connected"])
            cmd.assert_not_called()

    def test_capture_original_manual_ip_and_dns(self):
        def fake_command(*args):
            if "-listnetworkserviceorder" in args:
                return "(1) Ethernet\n(Hardware Port: Ethernet, Device: en0)\n"
            if "-getinfo" in args:
                return ("Manual Configuration\n"
                        "IP address: 198.51.100.36\n"
                        "Subnet mask: 255.255.255.240\n"
                        "Router: 198.51.100.33\n")
            if "-getdnsservers" in args:
                return "198.51.100.19\n"
            if "get" in args:
                return "route to: default\ninterface: en0\n"
            raise AssertionError(args)

        with mock.patch.object(recovery.os, "geteuid", return_value=0), \
             mock.patch.object(recovery, "command", side_effect=fake_command):
            self.assertEqual(recovery.capture(), STATIC)

    def test_fail_closed_on_missing_gateway(self):
        def fake_command(*args):
            if "-listnetworkserviceorder" in args:
                return "(1) Ethernet\n(Hardware Port: Ethernet, Device: en0)\n"
            if "-getinfo" in args:
                return ("Manual Configuration\nIP address: 198.51.100.36\n"
                        "Subnet mask: 255.255.255.240\nRouter: (null)\n")
            if "get" in args:
                return "interface: en0\n"
            return "198.51.100.19\n"
        with mock.patch.object(recovery.os, "geteuid", return_value=0), \
             mock.patch.object(recovery, "command", side_effect=fake_command):
            with self.assertRaisesRegex(ValueError, "CISCO_NETWORK_INVALID_IPV4"):
                recovery.capture()

    def test_checkpoint_is_root_private_and_not_overwritten(self):
        with mock.patch.object(recovery, "capture", return_value=STATIC):
            recovery.snapshot()
            self.assertEqual(json.loads(recovery.CHECKPOINT.read_text()), STATIC)
            self.assertEqual(recovery.CHECKPOINT.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(ValueError, "CISCO_NETWORK_CHECKPOINT_EXISTS"):
                recovery.snapshot()

    def test_existing_checkpoint_is_rejected_before_corrupt_network_capture(self):
        recovery.CHECKPOINT.write_text(json.dumps(STATIC))
        with mock.patch.object(recovery, "capture",
                               side_effect=ValueError("CISCO_NETWORK_INVALID_IPV4")) as capture:
            with self.assertRaisesRegex(ValueError, "CISCO_NETWORK_CHECKPOINT_EXISTS"):
                recovery.snapshot()
            capture.assert_not_called()
        self.assertEqual(json.loads(recovery.CHECKPOINT.read_text()), STATIC)

    def test_restore_preserves_unchanged_configuration(self):
        recovery.CHECKPOINT.write_text(json.dumps(STATIC))
        commands = []
        def fake_command(*args):
            commands.append(args)
            if args == (recovery.ROUTE, "-n", "get", "default"):
                return "gateway: 198.51.100.33\\ninterface: en0\\n".replace("\\n", "\n")
            if "-getinfo" in args:
                return ("Manual Configuration\nIP address: 198.51.100.36\n"
                        "Subnet mask: 255.255.255.240\nRouter: 198.51.100.33\n")
            if "-getdnsservers" in args:
                return "198.51.100.19\n"
            return ""
        with mock.patch.object(recovery.os, "geteuid", return_value=0), \
             mock.patch.object(recovery, "network_service_for_device", return_value="Ethernet"), \
             mock.patch.object(recovery, "read_checkpoint", return_value=STATIC), \
             mock.patch.object(recovery, "command", side_effect=fake_command):
            recovery.restore()
        self.assertFalse(recovery.CHECKPOINT.exists())
        self.assertFalse(any("-setmanual" in call or "-setdhcp" in call for call in commands))

    def test_restore_repairs_dhcp_regression(self):
        recovery.CHECKPOINT.write_text(json.dumps(STATIC))
        restored = [False]
        def fake_command(*args):
            if args == (recovery.ROUTE, "-n", "get", "default"):
                return "gateway: 198.51.100.33\\ninterface: en0\\n".replace("\\n", "\n")
            if "-getinfo" in args:
                if not restored[0]:
                    return ("DHCP Configuration\nIP address: 169.254.111.69\n"
                            "Subnet mask: 255.255.0.0\nRouter: (null)\n")
                return ("Manual Configuration\nIP address: 198.51.100.36\n"
                        "Subnet mask: 255.255.255.240\nRouter: 198.51.100.33\n")
            if "-setmanual" in args:
                restored[0] = True
            if "-getdnsservers" in args:
                return "198.51.100.19\n"
            return ""
        with mock.patch.object(recovery.os, "geteuid", return_value=0), \
             mock.patch.object(recovery, "network_service_for_device", return_value="Ethernet"), \
             mock.patch.object(recovery, "read_checkpoint", return_value=STATIC), \
             mock.patch.object(recovery, "command", side_effect=fake_command) as command:
            recovery.restore()
        self.assertTrue(restored[0])
        command.assert_any_call(
            recovery.NETWORKSETUP, "-setmanual", "Ethernet",
            "198.51.100.36", "255.255.255.240", "198.51.100.33")
        self.assertFalse(recovery.CHECKPOINT.exists())

    def test_watcher_does_nothing_without_checkpoint(self):
        with mock.patch.object(recovery, "restore") as restore, \
             mock.patch.object(recovery.os, "kill") as kill:
            recovery.watch(12345, 120)
            restore.assert_not_called()
            kill.assert_not_called()

    def test_orphan_stopper_rejects_unrelated_process(self):
        with mock.patch.object(recovery, "read_checkpoint",
                               return_value=dict(STATIC, tunnel_pid=2345)), \
             mock.patch.object(recovery.subprocess, "run",
                               return_value=mock.Mock(
                                   returncode=0,
                                   stdout="/usr/bin/python3 arbitrary_script.py")), \
             mock.patch.object(recovery.os, "kill") as kill:
            recovery.stop_orphaned_tunnel()
            kill.assert_not_called()

    def test_watchdog_recovers_after_launcher_crash(self):
        # Simulates a dead launcher and a surviving OpenConnect child.
        recovery.CHECKPOINT.write_text(json.dumps(STATIC))
        class Clock:
            def __init__(self):
                self.now = 0
            def monotonic(self):
                return self.now
            def sleep(self, seconds):
                self.now += seconds
        clock = Clock()
        with mock.patch("time.monotonic", side_effect=clock.monotonic), \
             mock.patch("time.sleep", side_effect=clock.sleep), \
             mock.patch.object(recovery.os, "kill", side_effect=ProcessLookupError), \
             mock.patch.object(recovery, "stop_orphaned_tunnel") as stop, \
             mock.patch.object(recovery, "restore") as restore:
            recovery.watch(12345, 120)
            stop.assert_called_once_with()
            restore.assert_called_once_with()

    def test_watchdog_recovers_at_deadline(self):
        # A live launcher past the deadline receives SIGTERM first.
        recovery.CHECKPOINT.write_text(json.dumps(STATIC))
        class Clock:
            def __init__(self):
                self.now = 0
            def monotonic(self):
                return self.now
            def sleep(self, seconds):
                self.now += seconds
        clock = Clock()
        with mock.patch("time.monotonic", side_effect=clock.monotonic), \
             mock.patch("time.sleep", side_effect=clock.sleep), \
             mock.patch.object(recovery.os, "kill") as kill, \
             mock.patch.object(recovery, "stop_orphaned_tunnel") as stop, \
             mock.patch.object(recovery, "restore") as restore:
            recovery.watch(12345, 10)
            self.assertTrue(any(call.args[0] == 12345 and
                                call.args[1] != 0 for call in kill.call_args_list))
            stop.assert_called_once_with()
            restore.assert_called_once_with()

    def test_default_route_check_rejects_vpn_gateway(self):
        wrong = "route to: default\ngateway: 10.99.0.1\ninterface: utun4\n"
        with mock.patch.object(recovery, "command", return_value=wrong):
            self.assertFalse(recovery.default_route_matches(STATIC))

    def test_unrestored_default_route_keeps_checkpoint(self):
        recovery.CHECKPOINT.write_text(json.dumps(STATIC))
        def fake_command(*args):
            if args == (recovery.ROUTE, "-n", "get", "default"):
                return "gateway: 10.99.0.1\ninterface: utun4\n"
            if "-getinfo" in args:
                return ("Manual Configuration\nIP address: 198.51.100.36\n"
                        "Subnet mask: 255.255.255.240\nRouter: 198.51.100.33\n")
            if "-getdnsservers" in args:
                return "198.51.100.19\n"
            raise AssertionError(args)
        with mock.patch.object(recovery.os, "geteuid", return_value=0), \
             mock.patch.object(recovery, "network_service_for_device", return_value="Ethernet"), \
             mock.patch.object(recovery, "read_checkpoint", return_value=STATIC), \
             mock.patch.object(recovery, "command", side_effect=fake_command):
            with self.assertRaisesRegex(
                ValueError, "CISCO_NETWORK_DEFAULT_ROUTE_UNVERIFIED"
            ):
                recovery.restore()
        self.assertTrue(recovery.CHECKPOINT.exists())

    def test_failed_restoration_preserves_checkpoint(self):
        recovery.CHECKPOINT.write_text(json.dumps(STATIC))
        with mock.patch.object(recovery.os, "geteuid", return_value=0), \
             mock.patch.object(recovery, "network_service_for_device", return_value="Ethernet"), \
             mock.patch.object(recovery, "read_checkpoint", return_value=STATIC), \
             mock.patch.object(recovery, "command", side_effect=ValueError(
                 "CISCO_NETWORK_COMMAND_FAILED")):
            with self.assertRaisesRegex(ValueError, "CISCO_NETWORK_COMMAND_FAILED"):
                recovery.restore()
        self.assertTrue(recovery.CHECKPOINT.exists())

    def test_bad_mode_does_not_change_network(self):
        entry = dict(STATIC, mode="invalid")
        recovery.CHECKPOINT.write_text(json.dumps(entry))
        with mock.patch.object(recovery.os, "geteuid", return_value=0), \
             mock.patch.object(recovery.os, "lstat",
                               return_value=mock.Mock(st_uid=0, st_mode=0o100600)), \
             mock.patch.object(recovery, "command") as command:
            with self.assertRaisesRegex(ValueError, "CISCO_NETWORK_CHECKPOINT_INVALID"):
                recovery.restore()
            command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
