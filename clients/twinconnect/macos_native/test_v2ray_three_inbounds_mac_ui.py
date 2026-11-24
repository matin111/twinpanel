"""Source-contract checks for the three selectable V2Ray inbounds."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
UI = (ROOT / "TwinConnectMacOSNativeDashboard.swift").read_text()
DIRECTORY = (ROOT / "TwinConnectMacOSNativeDirectory.swift").read_text()


class MacV2RayInboundSelectionTests(unittest.TestCase):
    def test_unsupported_inbound_is_shown_but_cannot_start_tun(self):
        self.assertIn('private func v2rayTunInboundSupported(_ id: String)', UI)
        self.assertIn('return id == "websocket_tls" || id == "tcp_tls"', UI)
        self.assertIn('choose.isEnabled = index >= 0 && tunSupported', UI)
        self.assertIn('XHTTP Reality requires a compatible Xray TUN engine.', UI)
        self.assertIn('!v2rayTunInboundSupported(activeV2RayInbound)', UI)

    def test_stale_selection_moves_only_within_same_server_to_real_profile(self):
        self.assertIn('private var activeV2RayInbound = "websocket_tls"', UI)
        self.assertIn('let available = found[serverID]', UI)
        self.assertIn('self.activeV2RayInbound = usable.id', UI)
        self.assertIn('self.persistCurrentSelection()', UI)

    def test_user_can_choose_each_inbound(self):
        self.assertIn('["tcp_tls", "websocket_tls", "xhttp_reality"]', UI)
        self.assertIn('["TCP TLS", "WebSocket TLS", "XHTTP Reality"]', UI)
        self.assertIn("selectServerV2RayInbound", UI)

    def test_faithful_windows_server_cards_no_synthetic_inbounds(self):
        self.assertIn("loadXrayInboundIndex", DIRECTORY)
        self.assertIn('allowedServerIDs.contains(nodeID)', DIRECTORY)
        self.assertIn('self.reviewedXrayVLESSUri(uri, profileID: id) != nil', DIRECTORY)
        self.assertIn('if !choices.isEmpty { found[nodeID] = choices }', DIRECTORY)
        self.assertIn('for inbound in xrayInboundIndex[server.id] ?? []', UI)
        self.assertIn('selectServerV2RayInbound', UI)
        self.assertIn('probeXrayInbound', UI)
        self.assertIn('countryName(code) + " · " +', UI)
        self.assertIn('v2rayInboundLabel(inbound.id) +', UI)
        self.assertNotIn('showV2RayInboundMenu', UI)
        self.assertNotIn('v2rayInboundChips()', UI)
        self.assertNotIn('serverIndex * v2rayInboundIDs.count + inboundIndex', UI)

    def test_real_profile_is_needed_before_selection(self):
        self.assertIn('xrayInboundIndex[nodeID]?.contains(where: { $0.id == inboundID })',
                      UI)
        self.assertIn('xrayIndexLoaded', UI)
        self.assertIn('No verified V2Ray profiles loaded.', UI)

    def test_selected_id_reaches_server_profile_selection(self):
        self.assertIn('v2rayInboundID: activeV2RayInbound', UI)
        self.assertIn('inboundID: v2rayInboundID ?? "websocket_tls"', DIRECTORY)
        self.assertIn('($0["id"] as? String) == inboundID', DIRECTORY)

    def test_server_does_not_silently_fall_back_to_other_inbound(self):
        self.assertNotIn('let priority = ["tcp_tls", "websocket_tls", "xhttp_reality"]', DIRECTORY)
        self.assertIn('profiles.filter({ ($0["id"] as? String) == inboundID }).count == 1',
                      DIRECTORY)


if __name__ == "__main__":
    unittest.main()