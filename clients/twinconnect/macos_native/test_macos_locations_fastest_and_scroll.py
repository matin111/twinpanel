"""Source contracts for stable scrolling and one-click fastest server."""
from pathlib import Path
import unittest

UI = Path(__file__).with_name("TwinConnectMacOSNativeDashboard.swift").read_text()


class LocationsInteractionTests(unittest.TestCase):
    def test_rebuild_preserves_locations_scroll_after_country_toggle(self):
        self.assertIn('private weak var locationsScrollView: NSScrollView?', UI)
        self.assertIn('locationsScrollOffset = max(0, previous.contentView.bounds.origin.y)', UI)
        self.assertIn('if tab == 1 { locationsScrollView = scroll }', UI)
        self.assertIn('let targetY = min(max(0, offset), maxY)', UI)
        self.assertIn('clip.scroll(to: NSPoint(x: 0, y: targetY))', UI)
        self.assertIn('scroll.reflectScrolledClipView(clip)', UI)
        body = UI[UI.index('@objc private func toggleLocationCountry('):
                  UI.index('@objc private func selectLocationServer(')]
        self.assertIn('view = build()', body)

    def test_server_selection_remains_in_locations(self):
        body = UI[UI.index('@objc private func selectServerV2RayInbound('):
                  UI.index('private func v2rayTunInboundSupported(')]
        self.assertIn('persistCurrentSelection()', body)
        self.assertNotIn('tab = 0', body)

    def test_fastest_triggers_measurement_not_manual_ping_dependency(self):
        body = UI[UI.index('@objc private func selectFastestMeasuredServer('):
                  UI.index('@objc private func pingAllServers(')]
        self.assertIn('measureAndSelectFastestV2Ray()', body)
        self.assertIn('pingNodes(candidates)', body)
        self.assertIn('fastestAutoSelectPending = true', body)
        self.assertNotIn('guard let best = eligible.min', body)
        self.assertIn('fastestBusy ? "◷  Finding fastest server…" : "✦  Fastest server"', UI)
        self.assertIn('fastestButton.isEnabled = availableForFastest', UI)

    def test_xray_fastest_only_checks_supported_actual_inbounds(self):
        body = UI[UI.index('private func measureAndSelectFastestV2Ray()'):
                  UI.index('@objc private func selectFastestMeasuredServer(')]
        self.assertIn('xrayInboundIndex[server.id] ?? []', body)
        self.assertIn('filter { v2rayTunInboundSupported($0.id) }', body)
        self.assertIn('measuredXrayTCPHandshake(choice.inbound)', body)
        self.assertIn('let limit = DispatchSemaphore(value: 4)', body)
        self.assertIn('self.activeV2RayInbound = choice.inbound.id', body)
        self.assertIn('self.applyFastestNode(choice.server)', body)
        self.assertIn('self.xrayIndexGeneration == profileGeneration', body)
        self.assertNotIn('xhttp_reality', body)

    def test_busy_or_connected_session_cannot_switch_server(self):
        body = UI[UI.index('@objc private func selectFastestMeasuredServer('):
                  UI.index('@objc private func pingAllServers(')]
        self.assertIn('!fullTunBusy, !fullTunActive', body)
        self.assertIn('!fullTunActive && !fullTunBusy', UI)


if __name__ == '__main__':
    unittest.main()