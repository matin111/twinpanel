"""Offline tests for independent WireGuard route recovery (no real routes)."""
import importlib.util
from pathlib import Path
import json
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "wireguard_management_route_guard",
    Path(__file__).with_name("wireguard_management_route_guard.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def ok(output="", code=0):
    return subprocess.CompletedProcess([], code, output, "")


class WatchdogTests(unittest.TestCase):
    def test_status_uptime_uses_verified_connection_not_lease_ttl(self):
        with patch.object(guard, "load", return_value={
                "mode": "leased", "connected_at": 5000,
                "deadline": 5100}), \
             patch.object(guard.time, "time", return_value=5050):
            self.assertEqual(json.loads(guard.status_uptime()),
                             {"state": "connected", "connected_at": 5000})

    def test_disconnected_tunnel_has_no_timer(self):
        with patch.object(guard, "load", return_value={}), \
             patch.object(guard.time, "time", return_value=5050):
            self.assertEqual(json.loads(guard.status_uptime()),
                             {"state": "disconnected"})

    def test_rejects_invalid_utun_before_tunnel_process_probe(self):
        with patch.object(guard, "run") as command:
            self.assertIsNone(guard.wireguard_endpoint(2255, "en0"))
            command.assert_not_called()

    def test_rejects_nonmatching_privileged_process(self):
        with patch.object(guard, "run", return_value=ok(
                "/bin/false -f utun15\n")):
            self.assertIsNone(guard.wireguard_endpoint(2255, "utun15"))

    def test_no_full_route_without_verified_peer_handshake(self):
        with patch.object(guard, "wireguard_endpoint", return_value=None), \
             patch.object(guard, "run") as command:
            self.assertEqual(guard.activate_full("utun15", 2555),
                             "WG_ENDPOINT_NOT_VERIFIED")
            command.assert_not_called()

    def test_no_arbitrary_destination_host_route(self):
        with patch.object(guard, "preflight") as preflight, \
             patch.object(guard, "run") as command:
            self.assertEqual(guard.probe_host("utun15", "9.9.9.9"),
                             "WG_PROBE_DESTINATION_REFUSED")
            preflight.assert_not_called()
            command.assert_not_called()

    def test_rollback_removes_only_owned_host_route(self):
        original = {"peers": [], "gateway": "185.236.39.33",
                    "interface": "en0", "deadline": 99999,
                    "probe_dest": "1.1.1.1", "probe_interface": "utun15"}
        routes = {"1.1.1.1"}
        def fake_run(*args):
            if args[:4] == ("/sbin/route", "-n", "delete", "-host"):
                routes.discard(args[4])
            return ok()
        with patch.object(guard, "load", return_value=original), \
             patch.object(guard, "exact_routes", side_effect=lambda: set(routes)), \
             patch.object(guard, "route", return_value={"interface": "utun15"}), \
             patch.object(guard, "run", side_effect=fake_run), \
             patch.object(guard, "STATE") as state_path:
            self.assertEqual(guard.rollback(),
                             "WG_MANAGEMENT_PIN_ROLLBACK_VERIFIED")
            state_path.unlink.assert_called_once()

    def test_refuses_parallel_legacy_vpn_after_handshake(self):
        with patch.object(guard, "wireguard_endpoint",
                          return_value="1.2.3.4"), \
             patch.object(guard, "load", return_value={}), \
             patch.object(guard.Path, "exists", return_value=True), \
             patch.object(guard, "preflight") as preflight:
            self.assertEqual(guard.activate_full("utun15", 2255),
                             "WG_OTHER_VPN_ACTIVE")
            preflight.assert_not_called()


if __name__ == "__main__":
    unittest.main()
