"""Source-contract tests for full-TUN pending state in the native macOS UI."""
from pathlib import Path
import unittest

UI = Path(__file__).with_name("TwinConnectMacOSNativeDashboard.swift").read_text()


class FullTunPendingIndicatorTests(unittest.TestCase):
    def test_hero_shows_connecting_during_tun_start(self):
        start = UI.index('private var verifiedHeroConnectionLabel: String')
        end = UI.index('private var verifiedNetworkConnectionLabel: String', start)
        block = UI[start:end]
        self.assertIn('if fullTunBusy && activeProtocol != "openvpn"', block)
        self.assertIn('return fullTunActive ? "◌  Disconnecting…" : "◌  Connecting…"', block)
        self.assertLess(block.index('if fullTunBusy &&'), block.index('return "◌  Offline"'))

    def test_network_status_matches_pending_state(self):
        start = UI.index('private var verifiedNetworkConnectionLabel: String')
        end = UI.index('private func connectPage()', start)
        block = UI[start:end]
        self.assertIn('return fullTunActive ? "Disconnecting…" : "Connecting…"', block)

    def test_button_shows_progress_without_faking_connected(self):
        self.assertIn('let connect = button(fullTunStatusUncertain ? "Checking…" :', UI)
        self.assertIn('fullTunBusy && activeProtocol != "openvpn" ?', UI)
        self.assertIn('Waiting for the TUN controller; connection not yet verified.', UI)
        self.assertIn('l2tpSystemRouteVerified || fullTunBusy ||', UI)
        self.assertIn('return "◌  Verifying internet" + fullTunConnectedSuffix', UI)


if __name__ == "__main__":
    unittest.main()