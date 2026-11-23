"""HTTPS proof must retry safely and never mark tunnel connected on ICMP alone."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
import unsigned_tun_daemon as daemon


class StubReply:
    status = 200

    def __init__(self, raw):
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, length):
        return self.raw


class HTTPSProofRecoveryTests(unittest.TestCase):
    def test_numeric_https_fallback_after_dns_failure(self):
        urls = []

        class Opener:
            def open(self, request, timeout):
                urls.append((request.full_url, timeout))
                if request.full_url.startswith("https://www."):
                    raise OSError('synthetic transient DNS timeout')
                return StubReply(b'ip=185.206.170.5\nloc=CA\n')

        with patch.object(daemon, "observe_route", return_value={
                    "route_state": "utun_route_observed_unverified"}), \
             patch.object(daemon.urllib.request, "build_opener", return_value=Opener()):
            result = daemon.probe_system_https()
        self.assertEqual(result["https_state"], "system_https_reachable")
        self.assertEqual(result["observed_exit_ip"], "185.206.170.5")
        self.assertFalse(result["system_vpn_verified"])
        self.assertEqual([url for url, _ in urls], [
            "https://www.cloudflare.com/cdn-cgi/trace",
            "https://1.1.1.1/cdn-cgi/trace"
        ])
        self.assertLess(sum(t for _, t in urls), 6)

    def test_bad_ip_and_unavailable_network_are_unverified(self):
        class Opener:
            def open(self, request, timeout):
                return StubReply(b'ip=127.0.0.1\n')
        with patch.object(daemon, "observe_route", return_value={
                    "route_state": "utun_route_observed_unverified"}), \
             patch.object(daemon.urllib.request, "build_opener", return_value=Opener()):
            result = daemon.probe_system_https()
        self.assertEqual(result, {"https_state": "unreachable"})

    def test_non_tun_route_never_opens_https(self):
        with patch.object(daemon, "observe_route", return_value={
                    "route_state": "not_utun_route"}), \
             patch.object(daemon.urllib.request, "build_opener") as opening:
            result = daemon.probe_system_https()
        self.assertEqual(result, {"https_state": "tun_route_not_observed"})
        opening.assert_not_called()

    def test_ui_does_not_falsely_claim_connected_when_unverified(self):
        code = (ROOT / 'TwinConnectMacOSNativeDashboard.swift').read_text()
        self.assertIn('return "◌  Verifying internet" + fullTunConnectedSuffix', code)
        self.assertIn('return "Checking HTTPS" + fullTunConnectedSuffix', code)
        self.assertIn('if self.fullTunHTTPSConnected,', code)
        self.assertIn('self.fullTunObservedExitIP = nil', code)
        self.assertIn('payload["https_state"] as? String == "system_https_reachable"', code)


if __name__ == '__main__':
    unittest.main()