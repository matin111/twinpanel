"""Offline regression contracts for native AppKit login and TUN error UX."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parent
DIRECTORY = SOURCE / "TwinConnectMacOSNativeDirectory.swift"
DASHBOARD = SOURCE / "TwinConnectMacOSNativeDashboard.swift"


class NativeSessionRestoreTests(unittest.TestCase):
    def test_keychain_not_password_or_userdefaults(self):
        directory = DIRECTORY.read_text(encoding="utf-8")
        self.assertIn("import Security", directory)
        for token in ("SecItemAdd", "SecItemCopyMatching", "SecItemUpdate",
                      "SecItemDelete", "kSecClassGenericPassword"):
            self.assertIn(token, directory)
        self.assertIn("refresh_token", directory)
        self.assertIn('payload: ["refresh_token": saved.token]', directory)
        self.assertNotIn('UserDefaults.standard.set(password', directory)
        self.assertNotIn("password: saved.", directory)

    def test_refresh_token_rotation_and_logout(self):
        directory = DIRECTORY.read_text(encoding="utf-8")
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn('v1/central-app/session/refresh', directory)
        self.assertIn('v1/central-app/session/brand', directory)
        self.assertIn("TwinMacNativeKeychain.save(next)", directory)
        self.assertIn("func clearSavedSession()", directory)
        self.assertIn("directory.clearSavedSession()", dashboard)
        self.assertIn("directory.restoreSavedSession", dashboard)
        self.assertIn("private var didAttemptSessionRestore = false", dashboard)

    def test_preflight_surfaces_safe_missing_profile_reason(self):
        directory = DIRECTORY.read_text(encoding="utf-8")
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn('"PROFILES_NOT_READY"', directory)
        self.assertIn('safeDetails.contains(candidate)', directory)
        self.assertIn('case .failure(let error):', dashboard)
        self.assertIn('TUN preflight blocked (', dashboard)
        self.assertIn('Hysteria2 is not entitled for this account.', dashboard)
        self.assertIn('no credentials included', dashboard)
        self.assertNotIn('profile or entitlement unavailable.', dashboard)

    def test_connect_button_is_primary_and_preflight_is_in_settings(self):
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        home = dashboard.split("private func connectPage() -> NSView {", 1)[1].split(
            "private func networkMetric(", 1)[0]
        settings = dashboard.split("private func settingsPage() -> NSView {", 1)[1].split(
            "private func expiryText(", 1)[0]
        self.assertIn('"ϟ    Connect     ›"', home)
        self.assertIn('"ϟ    Disconnect     ›"', home)
        self.assertIn('action: #selector(requestVPNConnection(_:))', home)
        self.assertNotIn('Check TUN readiness', home)
        self.assertIn('"Check TUN readiness"', settings)
        self.assertIn('action: #selector(unavailableConnect(_:))', settings)
        handler = dashboard.split(
            "@objc private func requestVPNConnection(", 1
        )[1].split("@objc private func unavailableConnect(", 1)[0]
        self.assertNotIn("prepareUnroutedHysteria2TUN", handler)
        self.assertIn("prepareLocalHysteria2", handler)
        self.assertIn("startVerifiedLocalProxy(profile)", handler)
        self.assertIn("Local proxy", handler)
        self.assertIn("stopVerifiedLocalProxy()", handler)
        self.assertNotIn("setGlobalProxy", handler)
        self.assertNotIn("startVPNTunnel", handler)
        self.assertIn('self.localProxyStatus = "Disconnected."', dashboard)

    def test_animation_and_real_traffic_metrics_are_proxy_scoped(self):
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        hero = dashboard.split("private final class TwinNativeNetworkFabric", 1)[1].split(
            "class TwinConnectMacOSNativeDashboard", 1)[0]
        self.assertIn("private let halo = CAShapeLayer()", hero)
        self.assertIn("CABasicAnimation", hero)
        self.assertIn("accessibilityDisplayShouldReduceMotion", hero)
        self.assertIn("fabric.proxyActive = localProxyActive", dashboard)
        self.assertIn('runLocalManager(["traffic"], root: root)', dashboard)
        self.assertIn("private func refreshTrafficMetrics()", dashboard)
        self.assertIn("downloadedTotalText?.stringValue", dashboard)
        self.assertIn("downloadSpeedText?.stringValue", dashboard)
        self.assertIn("self.trafficPollBusy = false", dashboard)
        self.assertIn("localProxyGeneration == generation", dashboard)
        self.assertNotIn("Local SOCKS proxy active (not VPN)", dashboard)
        self.assertNotIn("subtitle: pingDetails(selected)", dashboard)
        self.assertIn('"◉  Proxy active"', dashboard)
        self.assertIn('"ϟ    Connect     ›"', dashboard)
        monitor = dashboard.split("private func refreshTrafficMetrics()", 1)[1].split(
            "private func runLocalManager(", 1)[0]
        self.assertNotIn("self.view = self.build()", monitor)


if __name__ == "__main__":
    unittest.main()
