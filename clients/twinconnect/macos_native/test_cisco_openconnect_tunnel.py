"""Offline regression tests for the privileged OpenConnect TUN runner.

No tests here execute routes, launch OpenConnect, or require root.
"""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "cisco_openconnect_tunnel", HERE / "cisco_openconnect_tunnel.py")
import sys
sys.path.insert(0, str(HERE))
tun = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tun)


class CiscoTunnelTests(unittest.TestCase):
    def setUp(self):
        # Older runner tests exercise connection logic with the safety interlock
        # mocked. Production must remain fail closed until recovery is verified.
        enabled = mock.patch.object(tun, "CISCO_TUNNEL_ENABLED", True)
        enabled.start()
        self.addCleanup(enabled.stop)
        legacy = mock.patch.object(tun, "CISCO_UNPROTECTED_CONSOLE_TEST_ALLOWED", True)
        legacy.start()
        self.addCleanup(legacy.stop)
        # Offline unit tests must never touch or save real macOS network state.
        for method in ("snapshot_network", "restore_network",
                       "start_network_watchdog", "record_tunnel_pid"):
            patcher = mock.patch.object(tun, method)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_utun_counter_parsing_for_packet_flow_diagnostics(self):
        output = ("Name Mtu Network Address Ipkts Ierrs Ibytes Opkts Oerrs Obytes Coll\n"
                  "utun4 1300 <Link#23> 0 50 0 12345 44 0 6789 0\n")
        response = subprocess.CompletedProcess([], 0, output, "")
        with mock.patch.object(tun.subprocess, "run", return_value=response) as run:
            self.assertEqual(tun.cisco_tun_counters("utun4"), (12345, 6789))
            run.assert_called_once()
        with mock.patch.object(tun.subprocess, "run") as run:
            self.assertIsNone(tun.cisco_tun_counters("en0"))
            run.assert_not_called()

    def test_checkpoint_and_restore_wrap_successful_console_trial(self):
        with mock.patch.object(tun.os, "geteuid", return_value=0), \
             mock.patch.object(tun.os.path, "isfile", return_value=True), \
             mock.patch.object(tun.os, "access", return_value=True), \
             mock.patch.object(tun, "trusted_script", return_value=True), \
             mock.patch.object(tun, "trusted_openconnect_dependencies", return_value=True), \
             mock.patch.object(tun.subprocess, "Popen") as launch:
            child = launch.return_value
            child.stdin = mock.Mock()
            child.poll.return_value = 0
            child.wait.return_value = 0
            profile = {"host": "vpn.example.com", "port": 443,
                       "username": "alice", "password": "example",
                       "servercert": "sha256:" + "a" * 64}
            self.assertEqual(tun.run(profile, "console-test"), 0)
            tun.snapshot_network.assert_called_once_with()
            tun.start_network_watchdog.assert_called_once_with(True)
            tun.record_tunnel_pid.assert_called_once_with(child.pid)
            tun.restore_network.assert_called_once_with()

    def test_console_trial_denied_without_protected_management_route(self):
        # Even if the generic feature gate is enabled, an unprotected remote
        # console trial must not snapshot, alter routes or launch OpenConnect.
        with mock.patch.object(tun, "CISCO_UNPROTECTED_CONSOLE_TEST_ALLOWED", False), \
             mock.patch.object(tun.os, "geteuid", return_value=0), \
             mock.patch.object(tun, "trusted_script", return_value=True), \
             mock.patch.object(tun.os.path, "isfile", return_value=True), \
             mock.patch.object(tun.os, "access", return_value=True), \
             mock.patch.object(tun, "trusted_openconnect_dependencies", return_value=True), \
             mock.patch.object(tun.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(
                ValueError, "CISCO_CONSOLE_MANAGEMENT_ROUTE_REQUIRED"
            ):
                tun.run({}, "console-test")
            tun.snapshot_network.assert_not_called()
            launch.assert_not_called()

    def test_production_interlock_blocks_tunnel_before_network_changes(self):
        with mock.patch.object(tun, "CISCO_TUNNEL_ENABLED", False), \
             mock.patch.object(tun.os, "geteuid", return_value=0), \
             mock.patch.object(tun.subprocess, "run") as route, \
             mock.patch.object(tun.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(
                ValueError, "CISCO_TUNNEL_DISABLED_PENDING_NETWORK_RECOVERY"
            ):
                tun.run({}, "console-test")
            route.assert_not_called()
            launch.assert_not_called()

    def test_rejects_missing_or_private_management_address(self):
        for value in ("127.0.0.1", "192.168.1.2", "not-an-ip", "::1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                tun.management_route(value)

    def test_accepts_private_gateway_for_public_management_host(self):
        route = subprocess.CompletedProcess(
            [], 0,
            "route to: 8.8.8.8\ngateway: 192.168.0.1\ninterface: en0\n", "")
        with mock.patch.object(tun.subprocess, "run", return_value=route):
            gateway, interface = tun.management_route("8.8.8.8")
        self.assertEqual((gateway, interface), ("192.168.0.1", "en0"))

    def test_refuses_route_without_gateway(self):
        route = subprocess.CompletedProcess(
            [], 0, "route to: 8.8.8.8\ninterface: en0\n", "")
        with mock.patch.object(tun.subprocess, "run", return_value=route):
            with self.assertRaisesRegex(ValueError, "CISCO_MANAGEMENT_ROUTE_UNKNOWN"):
                tun.management_route("8.8.8.8")

    def test_desktop_mode_skips_management_route(self):
        # Locally approved desktop connections have no SSH/VNC management IP.
        with mock.patch.object(tun.os, "geteuid", return_value=0), \
             mock.patch.object(tun.os.path, "isfile", return_value=True), \
             mock.patch.object(tun.os, "access", return_value=True), \
             mock.patch.object(tun, "trusted_script", return_value=True), \
             mock.patch.object(tun, "trusted_openconnect_dependencies", return_value=True), \
             mock.patch.object(tun, "management_route") as route, \
             mock.patch.object(tun.subprocess, "run") as change_route, \
             mock.patch.object(tun.subprocess, "Popen") as launch:
            child = launch.return_value
            child.stdin = mock.Mock()
            child.wait.return_value = 0
            child.poll.return_value = 0
            profile = {"host": "vpn.example.com", "port": 443,
                       "username": "alice", "password": "example",
                       "servercert": "sha256:" + "a" * 64}
            self.assertEqual(tun.run(profile, "desktop"), 0)
            route.assert_not_called()
            change_route.assert_not_called()


    def test_requires_isolated_openconnect_before_launch(self):
        with mock.patch.object(tun.os, "geteuid", return_value=0), \
             mock.patch.object(tun, "trusted_script", return_value=True), \
             mock.patch.object(tun.os.path, "isfile", return_value=False), \
             mock.patch.object(tun.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(
                ValueError, "CISCO_ISOLATED_OPENCONNECT_MISSING"
            ):
                tun.run({}, "console-test")
            launch.assert_not_called()

    def test_refuses_writable_openconnect_dependencies(self):
        with mock.patch.object(tun.os, "geteuid", return_value=0), \
             mock.patch.object(tun.os.path, "isfile", return_value=True), \
             mock.patch.object(tun.os, "access", return_value=True), \
             mock.patch.object(tun, "trusted_script", return_value=True), \
             mock.patch.object(tun, "trusted_openconnect_dependencies", return_value=False), \
             mock.patch.object(tun.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(
                ValueError, "CISCO_UNTRUSTED_OPENCONNECT_DEPENDENCIES"
            ):
                tun.run({}, "console-test")
            launch.assert_not_called()

    def test_refuses_untrusted_vpn_script(self):
        with mock.patch.object(tun.os, "geteuid", return_value=0), \
             mock.patch.object(tun.os.path, "isfile", return_value=True), \
             mock.patch.object(tun.os, "access", return_value=True), \
             mock.patch.object(tun, "trusted_script", return_value=False), \
             mock.patch.object(tun.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError, "CISCO_TRUSTED_VPN_SCRIPT_REQUIRED"):
                tun.run({}, "desktop")
            launch.assert_not_called()

    def test_console_trial_times_out_and_cleans_child(self):
        with mock.patch.object(tun.os, "geteuid", return_value=0), \
             mock.patch.object(tun.os.path, "isfile", return_value=True), \
             mock.patch.object(tun.os, "access", return_value=True), \
             mock.patch.object(tun, "trusted_script", return_value=True), \
             mock.patch.object(tun, "trusted_openconnect_dependencies", return_value=True), \
             mock.patch.object(tun, "management_route") as route, \
             mock.patch.object(tun.subprocess, "run") as change_route, \
             mock.patch.object(tun.subprocess, "Popen") as launch:
            child = launch.return_value
            child.stdin = mock.Mock()
            child.wait.side_effect = [subprocess.TimeoutExpired("openconnect", 120), 0]
            child.poll.return_value = None
            profile = {"host": "vpn.example.com", "port": 443,
                       "username": "alice", "password": "example",
                       "servercert": "sha256:" + "a" * 64}
            self.assertEqual(tun.run(profile, "console-test"), 0)
            child.wait.assert_any_call(timeout=120)
            child.terminate.assert_called_once()
            route.assert_not_called()
            change_route.assert_not_called()


    def test_no_root_means_no_network_changes(self):
        with mock.patch.object(tun.os, "geteuid", return_value=501), \
             mock.patch.object(tun.subprocess, "run") as route, \
             mock.patch.object(tun.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError, "CISCO_ROOT_REQUIRED"):
                tun.run({}, "8.8.8.8")
            route.assert_not_called()
            launch.assert_not_called()

    def test_route_protection_failure_blocks_openconnect(self):
        failed = subprocess.CompletedProcess([], 1, "", "")
        with mock.patch.object(tun.os, "geteuid", return_value=0), \
             mock.patch.object(tun.os.path, "isfile", return_value=True), \
             mock.patch.object(tun.os, "access", return_value=True), \
             mock.patch.object(tun, "trusted_script", return_value=True), \
             mock.patch.object(tun, "trusted_openconnect_dependencies", return_value=True), \
             mock.patch.object(tun, "management_route", return_value=("192.168.0.1", "en0")), \
             mock.patch.object(tun.subprocess, "run", return_value=failed), \
             mock.patch.object(tun.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError,
                                       "CISCO_MANAGEMENT_ROUTE_PROTECTION_FAILED"):
                tun.run({"servercert": "sha256:" + "a" * 64}, "8.8.8.8")
            launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
