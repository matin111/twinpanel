#!/usr/bin/env python3
"""Offline contract tests: macOS must show AppKit before creating FlutterView."""
from __future__ import annotations

import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
NATIVE_FILES = (
    "install_macos_bridge.py",
    "TwinConnectMacOSVPNBridge.swift",
    "TwinConnectMacOSVPNControl.swift",
    "TwinConnectMacOSLibboxControl.swift",
    "TwinConnectMacOSMieruControl.swift",
    "TwinConnectMacOSMetalFallback.swift",
    "TwinConnectMacOSNativeDirectory.swift",
    "TwinConnectMacOSNativeDashboard.swift",
)

MAIN_WINDOW = """import Cocoa
import FlutterMacOS

class MainFlutterWindow: NSWindow {
  override func awakeFromNib() {
    let flutterViewController = FlutterViewController()
    let windowFrame = self.frame
    self.contentViewController = flutterViewController
    self.setFrame(windowFrame, display: true)
    RegisterGeneratedPlugins(registry: flutterViewController)
    super.awakeFromNib()
  }
}
"""


class MetalFallbackInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        native = self.root / "macos_native"
        runner = self.root / "macos/Runner"
        native.mkdir(parents=True)
        runner.mkdir(parents=True)
        for name in NATIVE_FILES:
            shutil.copy2(SOURCE / name, native / name)
        self.window = runner / "MainFlutterWindow.swift"
        self.window.write_text(MAIN_WINDOW, encoding="utf-8")
        (runner / "Info.plist").write_bytes(plistlib.dumps({"CFBundleName": "twinconnect"}))
        for name in ("DebugProfile.entitlements", "Release.entitlements"):
            (runner / name).write_bytes(plistlib.dumps({
                "com.apple.security.app-sandbox": True
            }))

    def install(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.root / "macos_native/install_macos_bridge.py")],
            capture_output=True, text=True, check=False
        )

    def test_metal_guard_before_flutter_view_is_idempotent(self) -> None:
        first = self.install()
        self.assertEqual(first.returncode, 0, first.stderr)
        generated = self.window.read_text(encoding="utf-8")
        self.assertEqual(generated.count("import Metal"), 1)
        self.assertEqual(
            generated.count("// TWINCONNECT_MACOS_METAL_PREFLIGHT_V1"), 1
        )
        self.assertEqual(
            generated.count("// TWINCONNECT_MACOS_METAL_FALLBACK_V1"), 1
        )
        self.assertLess(
            generated.index("MTLCreateSystemDefaultDevice()"),
            generated.index("FlutterViewController()")
        )
        self.assertIn("metal.makeCommandQueue() != nil else", generated)
        self.assertIn("self.titleVisibility = .hidden", generated)
        self.assertIn(
            "self.contentViewController = TwinConnectMacOSMetalFallback()",
            generated
        )
        self.assertIn("VPN controls require a verified Packet Tunnel", generated)
        self.assertIn("TWINCONNECT_MACOS_NATIVE_DIRECTORY_V1", generated)
        self.assertIn("TWINCONNECT_MACOS_NATIVE_DASHBOARD_V1", generated)
        self.assertIn("v1/central-app/public/login", generated)
        self.assertIn("v1/central-app/session/servers", generated)
        self.assertIn("v1/central-app/session/protocols", generated)
        self.assertIn("v1/central-app/session/plan", generated)
        self.assertIn("onUpdate: @escaping (TwinMacNativeSnapshot) -> Void", generated)
        self.assertIn('request(endpoint(panel, "v1/central-app/session/account")', generated)
        self.assertIn('request(endpoint(panel, "v1/central-app/session/plan")', generated)
        self.assertIn('request(endpoint(panel, "v1/central-app/session/servers")', generated)
        self.assertIn('request(endpoint(panel, "v1/central-app/session/protocols")', generated)
        self.assertIn("sectionsLoaded: loaded, errors: errors", generated)
        self.assertIn("isComplete: settled == 4", generated)
        self.assertIn("parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]", generated)
        self.assertIn("Panel: \\(count)/4 sections loaded", generated)
        self.assertIn("homeSubscriptionSummary()", generated)
        self.assertIn("Quick connect", generated)
        self.assertIn("Locations", generated)
        self.assertIn("Settings", generated)
        self.assertIn("Account", generated)
        self.assertIn("TwinNativeFlippedDocument", generated)
        self.assertIn("label.alignment = .left", generated)
        self.assertIn("child.widthAnchor.constraint(equalTo: column.widthAnchor)", generated)
        self.assertIn("reserved_renewal", generated)
        self.assertIn("TwinMacReservedRenewal", generated)
        self.assertIn("reservedRenewalCard", generated)
        # Ping UI must measure real, authorized node IPs; never a fake timer.
        self.assertIn('row["probe_ip"] as? String', generated)
        self.assertIn("TwinMacNativePing.validatedPublicIP", generated)
        self.assertIn("inet_pton(AF_INET", generated)
        self.assertIn("inet_pton(AF_INET6", generated)
        self.assertIn("let task = Process()", generated)
        self.assertIn('task.arguments = isV6 ? ["-n", "-c", "1", safeIP] :', generated)
        self.assertIn('["-n", "-c", "1", "-W", "1500", safeIP]', generated)
        self.assertIn('deadline: .now() + .seconds(4)', generated)
        self.assertIn('if task.isRunning { task.terminate() }', generated)
        self.assertIn("task.terminationStatus == 0", generated)
        self.assertIn("PING_REPLY_UNPARSEABLE", generated)
        self.assertIn("pingAllServers(_ sender: NSButton)", generated)
        self.assertIn("pingOneServer(_ sender: NSButton)", generated)
        self.assertIn("startNextNodePings()", generated)
        self.assertIn("nodePingBusy.count < 4", generated)
        self.assertIn("didAutoPing", generated)
        self.assertIn("pingText(server)", generated)
        self.assertIn("pingColor(server)", generated)
        self.assertIn("pingDetails(selected)", generated)
        self.assertIn("sidebarIcon(_ kind: Int)", generated)
        self.assertIn("control.image = sidebarIcon(index)", generated)
        self.assertIn("link.image = sidebarIcon(kind)", generated)
        self.assertIn("link.imagePosition = .imageAbove", generated)
        self.assertIn("control.contentTintColor", generated)
        self.assertIn("No public probe address supplied by the panel", generated)
        self.assertNotIn('action: #selector(unavailableConnect(_:)), mutedButton: true)\\n        ping.isEnabled = false', generated)
        self.assertIn("protocolChips()", generated)
        self.assertIn("selectProtocolChip(_ sender: NSButton)", generated)
        self.assertIn("searchLocations(_ sender: NSSearchField)", generated)
        self.assertIn("countryName(_ code: String)", generated)
        self.assertIn("networkStatusPage()", generated)
        self.assertIn("settingsPage()", generated)
        self.assertIn("accountPage()", generated)
        self.assertIn("TwinNativeNetworkFabric", generated)
        self.assertNotIn("TwinNativePowerRing", generated)
        self.assertIn('pair.distribution = .fillEqually', generated)
        self.assertIn('addPage(pair)', generated)
        self.assertIn('if availableWidth >= 790', generated)
        self.assertIn('sidebar.widthAnchor.constraint(equalToConstant: 258)', generated)
        # Hysteria2 SOCKS testing is a Settings-only diagnostic. The
        # Windows-like primary Connect button must never start a local proxy.
        self.assertIn('button("Test Hysteria2 SOCKS"', generated)
        self.assertIn('"ϟ    Connect now     ›"', generated)
        self.assertIn('action: #selector(unavailableConnect(_:)), primary: true', generated)
        self.assertIn('primaryProxyAction(_ sender: NSButton)', generated)
        self.assertIn('prepareLocalHysteria2', generated)
        # Regression: a login must show the AppKit dashboard even if
        # subscription refresh fails or takes time. Layout must not collapse.
        self.assertIn("sidebar.translatesAutoresizingMaskIntoConstraints = false", generated)
        self.assertIn("workspace.alignment = .leading", generated)
        self.assertIn("column.alignment = .leading", generated)
        self.assertNotIn(".alignment = .width", generated)
        self.assertIn("result.alignment = axis == .vertical ? .leading : .centerY", generated)
        self.assertIn("func addPage(_ page: NSView)", generated)
        self.assertIn("page.widthAnchor.constraint(equalTo: workspace.widthAnchor)", generated)
        self.assertIn("tile.widthAnchor.constraint(equalTo: group.widthAnchor)", generated)
        self.assertIn("section.widthAnchor.constraint(equalTo: wrapper.widthAnchor)", generated)
        self.assertIn("killSwitch.widthAnchor.constraint(equalTo: section.widthAnchor)", generated)
        self.assertIn("heroCard.widthAnchor.constraint(equalTo: content.widthAnchor)", generated)
        self.assertIn("reservedCard.widthAnchor.constraint(equalTo: content.widthAnchor)", generated)
        self.assertIn("usageCard.widthAnchor.constraint(equalTo: items.widthAnchor)", generated)
        self.assertIn("scroll.hasVerticalScroller = true", generated)
        self.assertIn("scroll.documentView = document", generated)
        self.assertIn("document.widthAnchor.constraint(equalTo: scroll.contentView.widthAnchor)", generated)
        self.assertIn("document.heightAnchor.constraint(greaterThanOrEqualTo:", generated)
        self.assertIn("self.view = self.build()\n                self.refreshData()", generated)
        self.assertIn("Panel synchronized: 4 of 4 sections.", generated)
        self.assertIn("data.errors.keys.sorted()", generated)
        login_code = generated.split("private func buildLogin(in root: NSView) {", 1)[1].split(
            "private func buildShell(in root: NSView) {", 1
        )[0]
        self.assertIn("glass.centerXAnchor.constraint(equalTo: root.centerXAnchor)", login_code)
        self.assertIn("glass.centerYAnchor.constraint(equalTo: root.centerYAnchor)", login_code)
        self.assertIn("form.widthAnchor.constraint(equalTo: glass.widthAnchor", login_code)
        self.assertIn("username.widthAnchor.constraint(equalTo: form.widthAnchor)", login_code)
        self.assertIn("password.widthAnchor.constraint(equalTo: form.widthAnchor)", login_code)
        self.assertIn("enter.widthAnchor.constraint(equalTo: form.widthAnchor)", login_code)
        self.assertIn('placeholder: "Username"', login_code)
        self.assertIn('placeholder: "Password"', login_code)
        self.assertIn('text("Welcome back", size: 27, weight: .bold)', login_code)
        self.assertNotIn("Secure app login", login_code)
        self.assertNotIn("TwinConnect app credentials", login_code)
        self.assertIn("NSGradient(colors:", generated)
        self.assertIn("VPN connection remains unavailable", generated)
        self.assertNotIn("startVPNTunnel(", generated.split("// TWINCONNECT_MACOS_METAL_FALLBACK_V1", 1)[-1])
        self.assertIn("TwinConnectMacOSVPNBridge.register(", generated)
        self.assertIn("RegisterGeneratedPlugins(registry: flutterViewController)",
                      generated)
        with (self.root / "macos/Runner/Info.plist").open("rb") as handle:
            info = plistlib.load(handle)
        self.assertEqual(info["TwinConnectDirectoryURL"], "https://panel.matindnspro.sbs")
        again = self.install()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(self.window.read_text(encoding="utf-8"), generated)
        for name in ("DebugProfile.entitlements", "Release.entitlements"):
            with (self.root / "macos/Runner" / name).open("rb") as handle:
                settings = plistlib.load(handle)
            self.assertTrue(settings["com.apple.security.network.client"])

    def test_node_aliases_and_account_scoped_selection_persist(self) -> None:
        source = (SOURCE / "TwinConnectMacOSNativeDashboard.swift").read_text(
            encoding="utf-8"
        )
        for token in (
            '"fi": ["fin", "finland"',
            '"de": ["des", "ger", "germany"',
            'aliases[code]?.contains(plain)',
            'import CryptoKit',
            'SHA256.hash(data: Data(identity.utf8))',
            'session.namespace + ":" + session.username.lowercased()',
            'self.restoreCurrentSelection(session)',
            'persistCurrentSelection()',
            'self.persistCurrentSelection()',
            'validIDs.contains($0.key)',
        ):
            self.assertIn(token, source)
        self.assertNotIn('UserDefaults.standard.set(session.accessToken', source)

    def test_server_ui_hides_raw_country_codes_and_blank_hero(self) -> None:
        source = (SOURCE / "TwinConnectMacOSNativeDashboard.swift").read_text(
            encoding="utf-8"
        )
        for token in (
            'friendlyServerName(_ server: TwinMacNativeServer,',
            '"  ·  Server " + String(index + 1)',
            'friendlyServerName(server, index: position)',
            'showAllProtocolChips.toggle()',
            '"All protocols (" + String(list.count)',
            'private final class TwinNativeNetworkFabric: NSView',
            'let centerBody = NSBezierPath(roundedRect:',
            '// Windows places the selected location only in Network Status,',
        ):
            self.assertIn(token, source)
        self.assertIn('pingDetails(server)', source)
        self.assertIn('selectLocationServer(_:)', source)

    def test_server_directory_uses_real_ping_and_selection_cards(self) -> None:
        source = (SOURCE / "TwinConnectMacOSNativeDashboard.swift").read_text(
            encoding="utf-8"
        )
        directory = source.split(
            "    private func locationsPage() -> NSView {", 1
        )[1].split("    private func createTable() -> NSView {", 1)[0]
        for token in (
            '"Server locations"', '"Search by server or country"',
            '"PROTOCOLS"', 'selected ? "✓" : "›"',
            'server.online', 'pingText(server)', 'pingColor(server)',
            'pingDetails(server)', 'pingOneServer(_:)',
            'selectLocationServer(_:)', 'toggleLocationCountry(_:)',
            'activeServer == server.id', 'probeIP != nil',
            'locationRowIDs = visible.map { $0.id }',
        ):
            self.assertIn(token, directory)
        self.assertNotIn('pingMs = 100', directory)
        self.assertNotIn('server.id.hashValue', directory)

    def test_windows_country_groups_and_fastest_use_real_icmp(self) -> None:
        source = (SOURCE / "TwinConnectMacOSNativeDashboard.swift").read_text(
            encoding="utf-8"
        )
        section = source.split(
            "    private func locationsPage() -> NSView {", 1
        )[1].split("    private func createTable() -> NSView {", 1)[0]
        for token in (
            'let countryHeader = stack(.horizontal, spacing: 10)',
            'let countryFlag = text(flag(code), size: 22',
            'let countryInfo = stack(spacing: 4)',
            'let headerCard = card([countryHeader]',
            'selectedHere ? "    ·    Selected" : ""',
            'selectFastestMeasuredServer(_:)',
            'nodePingResults[server.id]?.measuredMs != nil',
            '"✦  Fastest server  ·  Measure ping first"',
            'fastestButton.isEnabled = fastest != nil',
            'let select = button(selected ? "✓" : "›"',
        ):
            self.assertIn(token, section)
        self.assertIn('expandedCountries.insert(best.country.uppercased())',
                      source)
        self.assertNotIn('fakeLatency', section)

    def test_subscription_card_fills_entire_quick_connect_column(self) -> None:
        source = (SOURCE / "TwinConnectMacOSNativeDashboard.swift").read_text(
            encoding="utf-8"
        )
        connect = source.split(
            "    private func connectPage() -> NSView {", 1
        )[1].split("    private func networkMetric(", 1)[0]
        self.assertIn(
            "subscription.widthAnchor.constraint(equalTo: main.widthAnchor)",
            connect,
        )
        self.assertIn(
            'action: #selector(unavailableConnect(_:)), primary: true',
            connect,
        )
        self.assertNotIn('compactMetric("Public IP", value: "—")', connect)
        self.assertIn("usageCard.widthAnchor.constraint(equalTo: items.widthAnchor)",
                      source)

    def test_windows_subscription_uses_real_quota_thin_usage_rail(self) -> None:
        source = (SOURCE / "TwinConnectMacOSNativeDashboard.swift").read_text(
            encoding="utf-8"
        )
        body = source.split(
            "    private func homeSubscriptionSummary() -> NSView {", 1
        )[1].split("    private func filteredServers()", 1)[0]
        for token in (
            'track.heightAnchor.constraint(equalToConstant: 5)',
            'account.limitBytes > 0',
            'CGFloat(account.usedBytes) / CGFloat(account.limitBytes)',
            'filled.widthAnchor.constraint(equalTo: track.widthAnchor,',
            'usageCard.widthAnchor.constraint(equalTo: items.widthAnchor)',
        ):
            self.assertIn(token, body)
        self.assertNotIn('NSProgressIndicator()', body)

    def test_premium_glass_cards_and_gradient_buttons_use_live_appkit_layout(self) -> None:
        source = (SOURCE / "TwinConnectMacOSNativeDashboard.swift").read_text(
            encoding="utf-8"
        )
        for token in (
            "private final class TwinNativeGlassCard: NSView",
            "private final class TwinNativePremiumButton: NSButton",
            "private let glassGradient = CAGradientLayer()",
            "private let accentGradient = CAGradientLayer()",
            "glassGradient.frame = bounds",
            "accentGradient.frame = bounds",
            "let box = TwinNativeGlassCard(frame: .zero)",
            "let control = TwinNativePremiumButton(title: title",
            "control.setAccentGradient(",
            "connect.layer?.shadowOpacity = 0.17",
        ):
            self.assertIn(token, source)
        self.assertIn('pill("Disconnected", color: muted)', source)
        self.assertIn('networkMetric("Public IP", value: "—")', source)
        self.assertNotIn('pill("Tunnel active", color: sea)', source)

    def test_hysteria_app_lifetime_watchdog_is_always_enabled(self) -> None:
        source = (SOURCE / "TwinConnectMacOSNativeDashboard.swift").read_text(
            encoding="utf-8"
        )
        section = source.split(
            "    private func oneShotHysteria2Probe(_ config: Data) -> String {", 1
        )[1].split("    private func safeManagerReason", 1)[0]
        self.assertIn('"start", "hysteria2", file.path, "--owner-pid"', section)
        self.assertIn('String(ProcessInfo.processInfo.processIdentifier)', section)
        self.assertIn('let stopped = runLocalManager(["stop"], root: root)',
                      section)
        self.assertNotIn('systemPreferences', section)

    def test_connect_button_never_launches_diagnostic_proxy(self) -> None:
        source = (SOURCE / "TwinConnectMacOSNativeDashboard.swift").read_text(
            encoding="utf-8"
        )
        connect = source.split("    private func connectPage() -> NSView {", 1)[1].split(
            "    private func networkMetric(", 1
        )[0]
        settings = source.split("    private func settingsPage() -> NSView {", 1)[1].split(
            "    private func expiryText(", 1
        )[0]
        self.assertIn('"ϟ    Connect now     ›"', connect)
        self.assertIn('action: #selector(unavailableConnect(_:)), primary: true',
                      connect)
        self.assertNotIn('#selector(primaryProxyAction(_:))', connect)
        self.assertNotIn('#selector(stopLocalProxyNow(_:))', connect)
        self.assertIn('button("Test Hysteria2 SOCKS"', settings)
        self.assertIn('#selector(primaryProxyAction(_:))', settings)
        self.assertIn('button("■  Stop local proxy"', settings)
        self.assertIn('#selector(stopLocalProxyNow(_:))', settings)

    def test_tenant_colors_are_applied_to_every_glass_surface(self) -> None:
        source = (SOURCE / "TwinConnectMacOSNativeDashboard.swift").read_text(
            encoding="utf-8"
        )
        directory = (SOURCE / "TwinConnectMacOSNativeDirectory.swift").read_text(
            encoding="utf-8"
        )
        for token in (
            'let backgroundHex: String?',
            'let cardHex: String?',
            'brand["background_color"] as? String',
            'brand["card_color"] as? String',
            'brand["primary_color"]',
        ):
            self.assertIn(token, directory)
        for token in (
            'private func panelBackgroundColor() -> NSColor?',
            'private func panelCardColor() -> NSColor?',
            'return panelHexColor(accountSession?.accentHex) ?? teal',
            'box.apply(style, accent: tint(),',
            'side.apply(.sidebar, accent: tint(),',
            'background: panelBackgroundColor(), surface: panelCardColor()',
            'let brand = tint()',
            'control.setAccentGradient(upper.withAlphaComponent(0.90)',
            'enum Style: Equatable { case panel, inset, metric, sidebar }',
        ):
            self.assertIn(token, source)
        self.assertNotIn("legacyViolet() migration to teal", source)

    def test_status_pills_use_the_same_tenant_glass_as_cards(self) -> None:
        source = (SOURCE / "TwinConnectMacOSNativeDashboard.swift").read_text(
            encoding="utf-8"
        )
        pill = source.split("    private func pill(", 1)[1].split(
            "    private func button(", 1
        )[0]
        self.assertIn('let background = TwinNativeGlassCard(frame: .zero)',
                      pill)
        self.assertIn('background.apply(.inset, accent: color ?? tint()', pill)
        self.assertIn('surface: panelCardColor()', pill)
        self.assertNotIn('let background = NSView()', pill)

    def test_windows_background_is_cinematic_and_metal_free(self) -> None:
        source = (SOURCE / "TwinConnectMacOSNativeDashboard.swift").read_text(
            encoding="utf-8"
        )
        backdrop = source.split(
            "private final class TwinNativeBackdrop: NSView {", 1
        )[1].split("private final class TwinNativePremiumButton:", 1)[0]
        for token in (
            'private func radialLight(',
            'CGGradient(',
            'context.drawRadialGradient(',
            'radialLight(ctx,',
            'for index in 0..<11',
            'for index in 0..<26',
            'glow.withAlphaComponent(',
        ):
            self.assertIn(token, backdrop)
        self.assertNotIn('MTLCreateSystemDefaultDevice', backdrop)
        self.assertNotIn('URLSession', backdrop)

    def test_glass_panels_use_separate_windows_like_styles(self) -> None:
        source = (SOURCE / "TwinConnectMacOSNativeDashboard.swift").read_text(
            encoding="utf-8"
        )
        for token in (
            'enum Style { case panel, inset, metric, sidebar }',
            'private let upperEdge = CAGradientLayer()',
            'box.apply(style)',
            'side.apply(.sidebar)',
            'return card([items], radius: 20, padding: 14, style: .inset)',
            'let panel = card([content], radius: 17, padding: 14, style: .metric)',
        ):
            self.assertIn(token, source)

    def test_windows_network_cards_have_icon_plates_and_location_bar(self) -> None:
        source = (SOURCE / "TwinConnectMacOSNativeDashboard.swift").read_text(
            encoding="utf-8"
        )
        metric = source.split("    private func networkMetric(", 1)[1].split(
            "    private func networkStatusPage()", 1
        )[0]
        status = source.split("    private func networkStatusPage() -> NSView {", 1)[1].split(
            "    // Prefer a fresh local ICMP", 1
        )[0]
        for token in (
            "iconPlate.layer?.cornerRadius = 9",
            "iconPlate.widthAnchor.constraint(equalToConstant: 30)",
            "iconPlate.layer?.borderColor = sea.withAlphaComponent(0.34)",
        ):
            self.assertIn(token, metric)
        for token in (
            "let locationRow = stack(.horizontal, spacing: 9)",
            'let change = button("Locations  ›"',
            "let locationCard = card([locationRow], radius: 13, padding: 8,",
        ):
            self.assertIn(token, status)
        self.assertNotIn('button(location + "     ·     Locations', status)

    def test_emergency_stop_and_offline_animation_are_safe(self) -> None:
        source = (SOURCE / "TwinConnectMacOSNativeDashboard.swift").read_text(
            encoding="utf-8"
        )
        for token in (
            'var tunnelConnected = false',
            'guard tunnelConnected else { return }',
            '"■  Stop local proxy"',
            '#selector(stopLocalProxyNow(_:))',
            'private func stopLocalProxyNow',
            'self.runLocalManager(["stop"], root: root)',
            'Local proxy stopped. System VPN remains offline.',
        ):
            self.assertIn(token, source)
        self.assertNotIn('fabric.tunnelConnected = true', source)

    def test_sidebar_gradient_button_factory_retains_concrete_swift_type(self) -> None:
        source = (SOURCE / "TwinConnectMacOSNativeDashboard.swift").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "-> TwinNativePremiumButton {\n"
            "        let control = TwinNativePremiumButton(title: title,",
            source,
        )
        sidebar = source.split("    private func buildSidebar() -> NSView {", 1)[1].split(
            "    private func connectPage() -> NSView {", 1
        )[0]
        self.assertIn("control.setAccentGradient(", sidebar)
        self.assertIn("link.setAccentGradient(", sidebar)
        self.assertNotIn("-> NSButton {\n        let control = TwinNativePremiumButton", source)

    def test_sidebar_matches_windows_navigation_and_country_flag(self) -> None:
        source = (SOURCE / "TwinConnectMacOSNativeDashboard.swift").read_text(
            encoding="utf-8"
        )
        sidebar = source.split("    private func buildSidebar() -> NSView {", 1)[1].split(
            "    private func connectPage() -> NSView {", 1
        )[0]
        for token in (
            'let selectedLocation = snapshot?.servers.first { $0.id == activeServer }',
            'let selectedFlag = selectedLocation.map { flag($0.country) } ?? "🌐"',
            '"   " + selectedFlag + "     Locations"',
            'if index != 1 {',
            'control.setAccentGradient(',
            'link.setAccentGradient(',
            'control.layer?.cornerRadius = 16',
            'content.topAnchor.constraint(equalTo: side.topAnchor, constant: 27)',
            'content.bottomAnchor.constraint(equalTo: side.bottomAnchor,',
            'constant: -46',
        ):
            self.assertIn(token, sidebar)
        self.assertNotIn('spaced(side, content, inset: 17)', sidebar)
        self.assertIn('NSSize(width: 23, height: 23)', source)
        self.assertIn('// Windows sidebar uses the three horizontal sliders icon.', source)

    def test_windows_sidebar_language_and_account_logout(self) -> None:
        source = (SOURCE / "TwinConnectMacOSNativeDashboard.swift").read_text(
            encoding="utf-8"
        )
        side = source.split("    private func buildSidebar() -> NSView {", 1)[1].split(
            "    private func connectPage() -> NSView {", 1
        )[0]
        for token in (
            'button("◎   EN   ⌄"',
            'button("⚙", action: #selector(openLanguageSettings(_:))',
            'languageRow.widthAnchor.constraint(equalTo: content.widthAnchor)',
            'settingsRow.widthAnchor.constraint(equalTo: content.widthAnchor)',
        ):
            self.assertIn(token, side)
        self.assertNotIn('button("Sign out"', side)
        account = source.split("    private func accountPage() -> NSView {", 1)[1].split(
            "    private func compactMetric(", 1
        )[0]
        self.assertIn('button("Sign out", action: #selector(signOut(_:))', account)

    def test_quick_connect_scrolling_and_reference_geometry(self) -> None:
        source = (SOURCE / "TwinConnectMacOSNativeDashboard.swift").read_text(
            encoding="utf-8"
        )
        shell = source.split("    private func buildShell(in root: NSView) {", 1)[1].split(
            "    // Native vector glyphs", 1
        )[0]
        for token in (
            "root.addSubview(heading)",
            "scroll.topAnchor.constraint(equalTo: heading.bottomAnchor,",
            "scroll.autohidesScrollers = false",
            "scroll.hasVerticalScroller = true",
            "scroll.contentView.scroll(to: .zero)",
            "workspace.setContentHuggingPriority(.required, for: .vertical)",
            "document.heightAnchor.constraint(greaterThanOrEqualTo:",
        ):
            self.assertIn(token, shell)
        self.assertNotIn("heading.addArrangedSubview(pill", shell)
        self.assertNotIn("workspace.addArrangedSubview(heading)", shell)

    def test_windows_visual_parity_has_vector_hero_and_real_network_state(self) -> None:
        source = (SOURCE / "TwinConnectMacOSNativeDashboard.swift").read_text(
            encoding="utf-8"
        )
        for token in (
            'let centerBody = NSBezierPath(roundedRect:',
            'for index in 0..<17',
            'NSColor(calibratedRed: 0.24, green: 0.88, blue: 0.83,',
            'control.layer?.borderColor = primary ?',
            'box.layer?.shadowOpacity = 0.13',
            'let iconName: String',
            'selected ? "✓" : "›"',
            'pingDetails(server)',
            '"ϟ    Connect now     ›"',
            'pill("Disconnected", color: muted)',
            'networkMetric("Public IP", value: "—")',
            'networkMetric("Download", value: "—"',
            'networkMetric("Upload", value: "—"',
        ):
            self.assertIn(token, source)
        self.assertNotIn('pill("● Online", color: sea)', source)
        self.assertNotIn('startVPNTunnel(', source)

    def test_appkit_hysteria_keeps_authenticated_ca_without_tls_bypass(self) -> None:
        source = (self.root / "macos_native/TwinConnectMacOSNativeDirectory.swift").read_text(
            encoding="utf-8"
        )
        self.assertIn('tls["certificate"]', source)
        self.assertIn('tls["certificate_public_key_sha256"]', source)
        self.assertIn('tlsSettings["certificate"] = lines', source)
        self.assertIn('tlsSettings["certificate_public_key_sha256"] = pins', source)
        self.assertIn('tls["certificate_path"] != nil', source)
        self.assertIn('tls["insecure"] as? Bool != true', source)

    def test_refreshes_modified_appkit_source_without_duplicate_swift_types(self) -> None:
        self.assertEqual(self.install().returncode, 0)
        dashboard_path = self.root / "macos_native/TwinConnectMacOSNativeDashboard.swift"
        original = dashboard_path.read_text(encoding="utf-8")
        dashboard_path.write_text(
            original + "\n// UPDATED_TRACKED_APPKIT_SOURCE_SENTINEL\n",
            encoding="utf-8",
        )
        self.assertEqual(self.install().returncode, 0)
        generated = self.window.read_text(encoding="utf-8")
        self.assertEqual(
            generated.count("UPDATED_TRACKED_APPKIT_SOURCE_SENTINEL"), 1
        )
        self.assertEqual(
            generated.count("// TWINCONNECT_MACOS_NATIVE_DASHBOARD_V1"), 1
        )
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(
            self.window.read_text(encoding="utf-8"), generated
        )

    def test_replaces_old_diagnostics_only_fallback(self) -> None:
        first = self.install()
        self.assertEqual(first.returncode, 0, first.stderr)
        previous = self.window.read_text(encoding="utf-8")
        older = previous.split("// TWINCONNECT_MACOS_METAL_FALLBACK_V1", 1)[0]
        self.window.write_text(
            older + "// TWINCONNECT_MACOS_METAL_FALLBACK_V1\n" +
            "final class TwinConnectMacOSMetalFallback: NSViewController {}\n",
            encoding="utf-8"
        )
        refreshed = self.install()
        self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
        migrated = self.window.read_text(encoding="utf-8")
        self.assertNotIn("NSViewController {}", migrated)
        self.assertIn("TwinConnectMacOSNativeDashboard {}", migrated)
        self.assertEqual(migrated.count("class TwinConnectMacOSMetalFallback"), 1)

    def test_migrates_old_window_title_visibility_without_duplicates(self) -> None:
        self.assertEqual(self.install().returncode, 0)
        prior = self.window.read_text(encoding="utf-8")
        self.assertEqual(prior.count("self.titleVisibility = .hidden"), 1)
        self.window.write_text(
            prior.replace("      self.titleVisibility = .hidden\n", "", 1),
            encoding="utf-8"
        )
        fixed = self.install()
        self.assertEqual(fixed.returncode, 0, fixed.stderr)
        revised = self.window.read_text(encoding="utf-8")
        self.assertEqual(revised.count("self.titleVisibility = .hidden"), 1)
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.window.read_text(encoding="utf-8"), revised)

    def test_unknown_flutter_window_template_aborts_without_changes(self) -> None:
        self.window.write_text(
            MAIN_WINDOW.replace(
                "let flutterViewController = FlutterViewController()",
                "let controller = OtherFlutterView()"
            ), encoding="utf-8"
        )
        original = self.window.read_text(encoding="utf-8")
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unexpected macOS Flutter window startup", result.stderr)
        self.assertEqual(self.window.read_text(encoding="utf-8"), original)

    def test_missing_fallback_code_aborts_without_changes(self) -> None:
        (self.root / "macos_native/TwinConnectMacOSMetalFallback.swift").unlink()
        original = self.window.read_text(encoding="utf-8")
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.window.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
