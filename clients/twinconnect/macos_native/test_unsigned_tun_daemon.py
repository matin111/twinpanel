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

    def test_request_limits_and_actions(self):
        self.assertEqual(server.decode_request(b'{"action":"stop"}')["action"], "stop")
        for request in (b"", b'{"action":"shell"}', b'{"action":"status"' ,
                        b"x" * (server.MAX_REQUEST + 1)):
            with self.subTest(data=request[:15]):
                with self.assertRaises(ValueError):
                    server.decode_request(request)

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

    def test_unverified_engine_is_not_claimed_as_vpn_connected(self):
        self.assertIn("TUN engine running; system VPN NOT verified.", DASHBOARD)
        self.assertIn('"system_vpn_verified": False', (DIR /
                         "unsigned_tun_daemon.py").read_text())


if __name__ == "__main__":
    unittest.main()
