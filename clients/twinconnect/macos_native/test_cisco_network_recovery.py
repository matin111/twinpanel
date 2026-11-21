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
          "mode": "manual", "ip": "185.236.39.36",
          "mask": "255.255.255.240", "gateway": "185.236.39.33",
          "dns": ["185.236.39.19"]}


class CiscoRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(
            recovery, "CHECKPOINT", Path(self.tmp.name) / "checkpoint.json")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_capture_original_manual_ip_and_dns(self):
        def fake_command(*args):
            if "-listnetworkserviceorder" in args:
                return "(1) Ethernet\n(Hardware Port: Ethernet, Device: en0)\n"
            if "-getinfo" in args:
                return ("Manual Configuration\n"
                        "IP address: 185.236.39.36\n"
                        "Subnet mask: 255.255.255.240\n"
                        "Router: 185.236.39.33\n")
            if "-getdnsservers" in args:
                return "185.236.39.19\n"
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
                return ("Manual Configuration\nIP address: 185.236.39.36\n"
                        "Subnet mask: 255.255.255.240\nRouter: (null)\n")
            if "get" in args:
                return "interface: en0\n"
            return "185.236.39.19\n"
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

    def test_restore_preserves_unchanged_configuration(self):
        recovery.CHECKPOINT.write_text(json.dumps(STATIC))
        commands = []
        def fake_command(*args):
            commands.append(args)
            if "-getinfo" in args:
                return ("Manual Configuration\nIP address: 185.236.39.36\n"
                        "Subnet mask: 255.255.255.240\nRouter: 185.236.39.33\n")
            if "-getdnsservers" in args:
                return "185.236.39.19\n"
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
            if "-getinfo" in args:
                if not restored[0]:
                    return ("DHCP Configuration\nIP address: 169.254.111.69\n"
                            "Subnet mask: 255.255.0.0\nRouter: (null)\n")
                return ("Manual Configuration\nIP address: 185.236.39.36\n"
                        "Subnet mask: 255.255.255.240\nRouter: 185.236.39.33\n")
            if "-setmanual" in args:
                restored[0] = True
            if "-getdnsservers" in args:
                return "185.236.39.19\n"
            return ""
        with mock.patch.object(recovery.os, "geteuid", return_value=0), \
             mock.patch.object(recovery, "network_service_for_device", return_value="Ethernet"), \
             mock.patch.object(recovery, "read_checkpoint", return_value=STATIC), \
             mock.patch.object(recovery, "command", side_effect=fake_command) as command:
            recovery.restore()
        self.assertTrue(restored[0])
        command.assert_any_call(
            recovery.NETWORKSETUP, "-setmanual", "Ethernet",
            "185.236.39.36", "255.255.255.240", "185.236.39.33")
        self.assertFalse(recovery.CHECKPOINT.exists())

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
