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

    def test_connect_failure_is_visible_in_network_card(self):
        self.assertIn('private var connectionAttemptNotice: String?', UI)
        self.assertIn('if let notice = connectionAttemptNotice {', UI)
        self.assertIn('feedback.toolTip = notice', UI)
        self.assertIn('tab = 1', UI)
        self.assertIn('TUN connection failed: ', UI)

    def test_attested_trusttunnel_shows_correct_protocol_not_socks5(self):
        self.assertIn('private func attestedFullTunProtocol(', UI)
        self.assertIn('object["protocol_code"] as? String == "trusttunnel"', UI)
        self.assertIn('self.attestedFullTunProtocol(observed.1)', UI)
        self.assertIn('self.attestedFullTunProtocol(result.1)', UI)

    def test_connect_is_clickable_even_when_old_other_protocol_busy(self):
        home = UI.split('private func connectPage() -> NSView {', 1)[1].split(
            'private func networkMetric(', 1)[0]
        self.assertIn('connect.isEnabled = accountSession != nil && !fullTunBusy &&', home)
        self.assertNotIn('connect.isEnabled = accountSession != nil && !localProxyBusy', home)
        handler = UI.split('@objc private func requestVPNConnection(', 1)[1].split(
            '@objc ', 1)[0]
        self.assertIn('NSLog("TwinConnect AppKit: Connect button action received")',
                      handler)
        self.assertIn('if localProxyBusy || ciscoTunnelBusy ||', handler)
        self.assertIn('Connection unavailable: A previous connection operation', handler)
        self.assertIn('view = build()', handler)

    def test_network_card_exposes_selected_protocol(self):
        network = UI.split('private func networkStatusPage() -> NSView {', 1)[1]
        network = network.split('private func pingText(', 1)[0]
        self.assertIn('location + "  ·  " + activeCode', network)
        self.assertIn('connectionAttemptNotice', network)

    def test_button_shows_progress_without_faking_connected(self):
        self.assertIn('let connect = button(fullTunStatusUncertain ? "Checking…" :', UI)
        self.assertIn('fullTunBusy && activeProtocol != "openvpn" ?', UI)
        self.assertIn('Waiting for the TUN controller; connection not yet verified.', UI)
        self.assertIn('l2tpSystemRouteVerified || fullTunBusy ||', UI)
        self.assertIn('return "◌  Verifying internet" + fullTunConnectedSuffix', UI)


if __name__ == "__main__":
    unittest.main()
