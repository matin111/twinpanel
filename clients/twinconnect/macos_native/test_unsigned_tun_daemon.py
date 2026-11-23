"""Offline TUN daemon/client tests; never run VPN or modify routes."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))


def load(name):
    spec = importlib.util.spec_from_file_location(name, DIR / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


server = load("unsigned_tun_daemon")
client = load("unsigned_tun_client")
DASHBOARD = (DIR / "TwinConnectMacOSNativeDashboard.swift").read_text()


class TUNDaemonControlTests(unittest.TestCase):
    def test_engine_stderr_redacts_secret_bearing_error_details(self):
        cases = (
            (b'FATAL create tun: operation not permitted endpoint=secret',
             "TUN_ENGINE_PERMISSION_DENIED"),
            (b'FATAL initialize utun: no such device private=hidden',
             "TUN_ENGINE_INTERFACE_FAILED"),
            (b'FATAL interface error: address already in use uuid=secret',
             "TUN_ENGINE_CONFLICT"),
            (b'FATAL route add failed token=secret',
             "TUN_ENGINE_ROUTE_ERROR"),
            (b'FATAL unsupported feature private=secret',
             "TUN_ENGINE_RUNTIME_CONFIG_INVALID"),
        )
        for raw, expected in cases:
            with self.subTest(expected=expected):
                actual = server.classify_engine_stderr(raw)
                self.assertEqual(actual, expected)
                self.assertNotIn("secret", actual)
        self.assertEqual(server.classify_engine_stderr(b"unknown-private-key=secret"),
                         "TUN_ENGINE_EXITED_BEFORE_ROUTE")

    def test_engine_errors_are_specific_and_do_not_expose_secrets(self):
        source = (DIR / "unsigned_tun_daemon.py").read_text()
        self.assertIn('raise ValueError("SINGBOX_CONFIG_REJECTED")', source)
        self.assertIn('raise ValueError("SINGBOX_CONFIG_CHECK_TIMEOUT")', source)
        self.assertIn('raise ValueError(error_code)', source)
        self.assertIn('classify_engine_stderr(', source)
        self.assertIn('raise ValueError("TUN_WATCHDOG_EXITED_BEFORE_ROUTE")', source)
        self.assertIn('for _ in range(32):', source)

    def test_vps_trial_session_is_bounded(self):
        with mock.patch.object(server, "APPROVAL",
                               mock.Mock(read_text=lambda **_: "VPS_OOB_CONSOLE_45_SECONDS")):
            self.assertEqual(server.session_limit(), 45)
        with mock.patch.object(server, "APPROVAL",
                               mock.Mock(read_text=lambda **_: "LOCAL_MAC_WITH_RECOVERY")):
            self.assertEqual(server.session_limit(), 600)

    def test_extended_vps_mode_keeps_management_route_guard(self):
        with mock.patch.object(server, "APPROVAL",
                               mock.Mock(read_text=lambda **_:
                                         "VPS_OOB_CONSOLE_LONG_SESSION_30_DAYS")):
            self.assertTrue(server.vps_mode())
            self.assertEqual(server.session_limit(), 30 * 24 * 60 * 60)
        with mock.patch.object(server, "APPROVAL",
                               mock.Mock(read_text=lambda **_:
                                         "VPS_OOB_CONSOLE_45_SECONDS")):
            self.assertTrue(server.vps_mode())
        with mock.patch.object(server, "APPROVAL",
                               mock.Mock(read_text=lambda **_: "LOCAL_MAC_WITH_RECOVERY")):
            self.assertFalse(server.vps_mode())
        source = (DIR / "unsigned_tun_daemon.py").read_text()
        self.assertIn("if vps_mode():", source)
        self.assertIn("profile = guard_candidate(", source)
        self.assertIn("dns_servers=system_dns_resolvers()", source)
        self.assertNotIn("if session_limit() == VPS_SESSION:", source)

    def test_unix_peer_uid_uses_kernel_credentials(self):
        import socket
        with mock.patch.object(server.sys, "platform", "darwin"):
            left, right = socket.socketpair()
            try:
                self.assertEqual(server.unix_peer_uid(left), os.getuid())
                self.assertEqual(server.unix_peer_uid(right), os.getuid())
            finally:
                left.close()
                right.close()

    def test_authorized_peer_checks_console_owner(self):
        import socket
        with mock.patch.object(server.sys, "platform", "darwin"), \
             mock.patch.object(server.os, "stat") as stat_call:
            stat_call.return_value.st_uid = os.getuid()
            left, right = socket.socketpair()
            try:
                self.assertTrue(server.authorized_peer(left))
                stat_call.return_value.st_uid = os.getuid() + 1
                self.assertFalse(server.authorized_peer(left))
            finally:
                left.close()
                right.close()

    def test_console_owner_required(self):
        self.assertTrue(server.allowed_uid(501, 501))
        self.assertFalse(server.allowed_uid(502, 501))
        self.assertFalse(server.allowed_uid(0, 501))
        self.assertFalse(server.allowed_uid(501, 0))

    def test_start_rejects_invalid_config_without_engine(self):
        session = server.Session()
        with mock.patch.object(server.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(ValueError, "TUN_CONFIG_NOT_OBJECT"):
                session.start(501, "not a profile")
            spawn.assert_not_called()

    def test_stop_is_limited_to_owner(self):
        session = server.Session()
        session.owner = 501
        with self.assertRaisesRegex(ValueError, "TUN_OWNER_MISMATCH"):
            session.stop(502)

    def test_reap_exited_process(self):
        session = server.Session()
        proc = mock.Mock()
        proc.poll.return_value = 1
        session.process = proc
        session.owner = 501
        self.assertEqual(session.status()["state"], "stopped")
        self.assertIsNone(session.owner)

    def test_timeout_terminates_only_owned_engine_process_group(self):
        session = server.Session()
        proc = mock.Mock()
        proc.poll.return_value = None
        proc.pid = 20099
        session.process = proc
        session.owner = 501
        session.started = 1
        with mock.patch.object(server.time, "monotonic",
                               return_value=server.MAX_SESSION + 3), \
             mock.patch.object(server.os, "killpg") as terminate:
            self.assertEqual(session.status()["state"], "stopped")
            terminate.assert_called_once_with(20099, server.signal.SIGTERM)

    def test_console_logout_stops_engine_and_clears_owner(self):
        session = server.Session()
        proc = mock.Mock()
        proc.poll.return_value = None
        proc.pid = 20098
        session.process = proc
        session.owner = 501
        session.started = 10
        with mock.patch.object(server.os, "stat") as stat_call, \
             mock.patch.object(server.os, "killpg") as kill, \
             mock.patch.object(server.time, "monotonic", return_value=20):
            stat_call.return_value.st_uid = 502
            self.assertEqual(session.status()["state"], "stopped")
            kill.assert_called_once_with(proc.pid, server.signal.SIGTERM)
            self.assertIsNone(session.owner)

    def test_console_same_owner_keeps_engine(self):
        session = server.Session()
        proc = mock.Mock()
        proc.poll.return_value = None
        session.process = proc
        session.owner = 501
        session.started = 10
        with mock.patch.object(server.os, "stat") as stat_call, \
             mock.patch.object(server.time, "monotonic", return_value=20), \
             mock.patch.object(server.os, "killpg") as kill:
            stat_call.return_value.st_uid = 501
            self.assertEqual(session.status()["state"], "engine_running_unverified")
            kill.assert_not_called()

    def test_untrusted_fake_socket_rejected_without_send(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = Path(folder) / "fake.sock"
            fake.write_text("not an actual UNIX domain socket")
            with self.assertRaisesRegex(ValueError, "TUN_SERVICE_UNTRUSTED"):
                client.query("start", {"outbounds": []}, socket_path=fake)

    def test_route_observer_reports_utun_without_claiming_egress(self):
        response = mock.Mock(returncode=0, stdout=(
            "   route to: 1.1.1.1\n"
            "interface: utun5\n"))
        with mock.patch.object(server.platform, "system", return_value="Darwin"), \
             mock.patch.object(server.subprocess, "run", return_value=response):
            self.assertEqual(
                server.observe_route()["route_state"],
                "utun_route_observed_unverified")

    def test_route_observer_distinguishes_direct_egress(self):
        response = mock.Mock(returncode=0, stdout="interface: en0\n")
        with mock.patch.object(server.platform, "system", return_value="Darwin"), \
             mock.patch.object(server.subprocess, "run", return_value=response):
            self.assertEqual(server.observe_route()["route_state"],
                             "not_utun_route")

    def test_route_observer_handles_failures(self):
        with mock.patch.object(server.platform, "system", return_value="Darwin"), \
             mock.patch.object(server.subprocess, "run",
                               side_effect=server.subprocess.TimeoutExpired("route", 3)):
            self.assertEqual(server.observe_route()["route_state"], "unavailable")

    def test_start_fail_closed_on_preexisting_tun_route(self):
        session = server.Session()
        with mock.patch.object(server, "observe_route",
                return_value={"route_state": "utun_route_observed_unverified"}), \
             mock.patch.object(server.os, "open") as open_file:
            with self.assertRaisesRegex(ValueError, "EXISTING_TUN_ROUTE_AMBIGUOUS"):
                session.start(501, {"inbounds": [], "outbounds": []})
            open_file.assert_not_called()

    def test_daemon_never_claims_route_as_verified_vpn(self):
        source = (DIR / "unsigned_tun_daemon.py").read_text()
        self.assertIn('"system_vpn_verified": False', source)
        self.assertIn("TUN_ROUTE_NOT_ESTABLISHED", source)

    def test_request_limits_and_actions(self):
        self.assertEqual(server.decode_request(b'{"action":"stop"}')["action"], "stop")
        for request in (b"", b'{"action":"shell"}', b'{"action":"status"' ,
                        b"x" * (server.MAX_REQUEST + 1)):
            with self.subTest(data=request[:15]):
                with self.assertRaises(ValueError):
                    server.decode_request(request)

    def test_start_has_longer_timeout_than_status(self):
        source = (DIR / "unsigned_tun_client.py").read_text()
        self.assertIn('client.settimeout(30 if action == "start" else 6)', source)

    def test_client_fail_closed_without_service(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "TUN_SERVICE_UNAVAILABLE"):
                client.query("status", socket_path=Path(folder) / "none.sock")

    def test_client_does_not_log_credentials(self):
        payload = client.encode_request("start",
                    {"outbounds": [{"password": "secret-value"}]})
        self.assertIn(b"secret-value", payload)
        self.assertNotIn(b"secret-value", client.encode_request("status"))

    def test_native_primary_button_uses_tun_only_if_service_present(self):
        section = DASHBOARD.split("@objc private func requestVPNConnection(", 1)[1]
        self.assertIn("if fullTunServicePresent()", section)
        self.assertIn("startFullTun(", section)
        self.assertIn("stopFullTun()", section)
        self.assertIn("self.startVerifiedLocalProxy(", section)

    def test_app_refreshes_stale_tun_state(self):
        self.assertIn("private func refreshFullTunStatus()", DASHBOARD)
        self.assertIn('self.runFullTunClient("status")', DASHBOARD)
        self.assertIn('self.status = "TUN session stopped or engine exited."', DASHBOARD)

    def test_unverified_engine_is_not_claimed_as_vpn_connected(self):
        self.assertIn("TUN route running; checking HTTPS.", DASHBOARD)
        self.assertIn('if fullTunHTTPSConnected { return "◉  Connected" }', DASHBOARD)
        self.assertIn('if fullTunActive { return "◉  TUN running · unverified" }', DASHBOARD)
        self.assertIn('"system_vpn_verified": False', (DIR /
                         "unsigned_tun_daemon.py").read_text())


if __name__ == "__main__":
    unittest.main()