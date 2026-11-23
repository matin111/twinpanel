"""Source-contract checks for the three selectable V2Ray inbounds."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
UI = (ROOT / "TwinConnectMacOSNativeDashboard.swift").read_text()
DIRECTORY = (ROOT / "TwinConnectMacOSNativeDirectory.swift").read_text()


class MacV2RayInboundSelectionTests(unittest.TestCase):
    def test_user_can_choose_each_inbound(self):
        self.assertIn('["tcp_tls", "websocket_tls", "xhttp_reality"]', UI)
        self.assertIn('["TCP TLS", "WebSocket TLS", "XHTTP Reality"]', UI)
        self.assertIn("selectV2RayInbound", UI)

    def test_choices_in_quick_connect_and_locations(self):
        self.assertGreaterEqual(UI.count('v2rayInboundChips()'), 3)

    def test_selected_id_reaches_server_profile_selection(self):
        self.assertIn('v2rayInboundID: activeV2RayInbound', UI)
        self.assertIn('inboundID: v2rayInboundID ?? "tcp_tls"', DIRECTORY)
        self.assertIn('($0["id"] as? String) == inboundID', DIRECTORY)

    def test_server_does_not_silently_fall_back_to_other_inbound(self):
        self.assertNotIn('let priority = ["tcp_tls", "websocket_tls", "xhttp_reality"]', DIRECTORY)
        self.assertIn('profiles.filter({ ($0["id"] as? String) == inboundID }).count == 1',
                      DIRECTORY)


if __name__ == "__main__":
    unittest.main()