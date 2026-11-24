"""Offline tests for optional real HTTPS probe; no network traffic."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
spec = importlib.util.spec_from_file_location(
    "unsigned_tun_daemon", DIR / "unsigned_tun_daemon.py")
daemon = importlib.util.module_from_spec(spec)
spec.loader.exec_module(daemon)


class HTTPSProbeTests(unittest.TestCase):
    def test_no_https_call_without_utun_route(self):
        with mock.patch.object(daemon, "observe_route",
                               return_value={"route_state": "not_utun_route"}), \
             mock.patch.object(daemon.urllib.request, "build_opener") as opener:
            self.assertEqual(daemon.probe_system_https()["https_state"],
                             "tun_route_not_observed")
            opener.assert_not_called()

    def test_https_probe_reports_actual_global_exit_ip(self):
        response = mock.MagicMock()
        response.status = 200
        response.read.return_value = b"ip=1.1.1.1\nloc=US\n"
        opener = mock.MagicMock()
        opener.open.return_value.__enter__.return_value = response
        with mock.patch.object(daemon, "observe_route",
                               return_value={"route_state":
                                             "utun_route_observed_unverified"}), \
             mock.patch.object(daemon.urllib.request, "build_opener",
                               return_value=opener):
            result = daemon.probe_system_https()
            self.assertEqual(result["observed_exit_ip"], "1.1.1.1")
            self.assertEqual(result["https_state"], "system_https_reachable")
            self.assertFalse(result["system_vpn_verified"])

    def test_unreachable_route_does_not_claim_connected(self):
        with mock.patch.object(daemon, "observe_route",
                               return_value={"route_state":
                                             "utun_route_observed_unverified"}), \
             mock.patch.object(daemon.urllib.request, "build_opener",
                               side_effect=OSError("offline")):
            result = daemon.probe_system_https()
            self.assertEqual(result["https_state"], "unreachable")

    def test_probe_not_run_in_status_or_automatically(self):
        source = (DIR / "unsigned_tun_daemon.py").read_text()
        self.assertIn('elif action == "probe":', source)
        self.assertIn('result.update(probe_system_https())', source)
        self.assertIn('if action == "status":', source)
        self.assertIn('"system_vpn_verified": False', source)


if __name__ == "__main__":
    unittest.main()
