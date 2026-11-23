"""Contract tests for truthful macOS unsigned TUN presentation."""
from pathlib import Path
import unittest

UI = Path(__file__).with_name("TwinConnectMacOSNativeDashboard.swift").read_text()

class UnsignedTunStatusTests(unittest.TestCase):
    def test_only_kernel_route_and_owner_allow_running_indicator(self):
        self.assertIn('private func tunRouteIsRunning(_ raw: String)', UI)
        self.assertIn('payload["owner_present"] as? Bool == true', UI)
        self.assertIn('payload["route_state"] as? String == "utun_route_observed_unverified"', UI)

    def test_ambiguous_start_reconciles_without_starting_another_engine(self):
        self.assertIn('self.runFullTunClient("status") : response', UI)
        self.assertIn('self.tunRouteIsRunning(observed.1)', UI)

    def test_https_exit_ip_is_not_claimed_as_verified_system_vpn(self):
        self.assertIn('self.fullTunObservedExitIP = address', UI)
        self.assertIn('fullTunActive ? (fullTunObservedExitIP ?? "—")', UI)
        self.assertIn('Full VPN not yet verified.', UI)
        self.assertIn('TUN trial', UI)

    def test_stopped_trial_clears_stale_ip_and_timer(self):
        self.assertIn('self.fullTunObservedExitIP = nil', UI)
        self.assertIn('self.fullTunStartedAt = nil', UI)
        self.assertIn('TUN service stopped or unavailable.', UI)

if __name__ == "__main__":
    unittest.main()