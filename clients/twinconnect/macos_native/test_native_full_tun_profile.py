"""Offline native TUN profile integration contract. Never changes networking."""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parent /
          "TwinConnectMacOSNativeDirectory.swift").read_text(encoding="utf-8")
DASHBOARD = (Path(__file__).resolve().parent /
             "TwinConnectMacOSNativeDashboard.swift").read_text(encoding="utf-8")


class NativeFullTUNProfileTests(unittest.TestCase):
    def test_entitled_selected_profile_only(self):
        self.assertIn("func prepareFullTUNCandidate(", SOURCE)
        self.assertIn("prepareLocalSingBox(session, serverID: serverID,", SOURCE)
        self.assertIn("protocolCode: protocolCode) { result in", SOURCE)

    def test_full_tun_route_and_no_auto_redirect(self):
        section = SOURCE.split("func prepareFullTUNCandidate(", 1)[1].split(
            "private func localHysteria2Config(", 1)[0]
        for required in ('"type": "tun"', '"auto_route": true',
                         '"auto_redirect": false', '"strict_route": false',
                         '"route": ["final": "proxy"]'):
            self.assertIn(required, section)

    def test_denies_direct_fallback_and_unreviewed_dns(self):
        section = SOURCE.split("func prepareFullTUNCandidate(", 1)[1].split(
            "private func localHysteria2Config(", 1)[0]
        for required in ('kind == "direct"', 'kind == "block"',
                         'kind == "dns"', 'proxy["dns"] == nil',
                         'proxy["experimental"] == nil'):
            self.assertIn(required, section)

    def test_shadowtls_detour_preserved(self):
        section = SOURCE.split("func prepareFullTUNCandidate(", 1)[1].split(
            "private func localHysteria2Config(", 1)[0]
        self.assertIn('"outbounds": outbounds', section)

    def test_main_connect_still_uses_verified_proxy(self):
        section = DASHBOARD.split(
            "@objc private func requestVPNConnection(", 1)[1].split(
            "private func startVerifiedLocalProxy(", 1)[0]
        self.assertIn("self.startVerifiedLocalProxy(", section)
        self.assertNotIn("startFullTUN", section)


if __name__ == "__main__":
    unittest.main()
