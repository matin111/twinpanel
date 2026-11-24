"""Offline contract checks for the native settings screen."""
from pathlib import Path
import unittest
SOURCE=Path(__file__).with_name("TwinConnectMacOSNativeDashboard.swift").read_text()
PAGE=SOURCE.split("private func settingsPage() -> NSView {",1)[1].split("@objc private func changeNativeAppearance",1)[0]

class ProductionSettingsTests(unittest.TestCase):
    def test_no_inactive_security_or_test_controls(self):
        for label in ("Unavailable", "Split Tunneling", "DNS protection",
                      "Auto reconnect", "Test selected SOCKS", "Check TUN readiness",
                      "Test Cisco authentication", "App language"):
            self.assertNotIn(label,PAGE)
    def test_real_persistent_theme(self):
        self.assertIn('NSSegmentedControl(labels: ["Light", "Dark"]',PAGE)
        self.assertIn('#selector(changeNativeAppearance(_:))',PAGE)
        self.assertIn('UserDefaults.standard.set(sender.selectedSegment == 0 ? "light" : "dark"',SOURCE)
        self.assertIn('root.appearance = NSAppearance(named: lightAppearance ? .aqua : .darkAqua)',SOURCE)
        self.assertIn('label.textColor = color ?? foreground',SOURCE)
        self.assertIn('if TwinNativePreferences.light {',SOURCE)
    def test_real_motion_preference(self):
        self.assertIn('#selector(changeNativeMotion(_:))',PAGE)
        self.assertIn('UserDefaults.standard.set(sender.state == .on',SOURCE)
        self.assertGreaterEqual(SOURCE.count('!TwinNativePreferences.reducedMotion'),3)
    def test_refresh_and_report_have_handlers(self):
        self.assertIn('#selector(refresh(_:))',PAGE)
        self.assertIn('#selector(copyDiagnostics(_:))',PAGE)
        report=SOURCE.split('@objc private func copyDiagnostics(',1)[1]
        self.assertIn('verifiedNetworkConnectionLabel',report)
        self.assertNotIn('System VPN: offline',report)
        self.assertNotIn('accessToken',report)
        self.assertNotIn('username',report)
    def test_emergency_controls_only_active(self):
        self.assertIn('if ciscoTunnelTask != nil {',PAGE)
        self.assertIn('if localProxyActive {',PAGE)

if __name__=="__main__": unittest.main()
