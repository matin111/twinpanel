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
        self.assertIn('Connect now', generated)
        # Regression: a login must show the AppKit dashboard even if
        # subscription refresh fails or takes time. Layout must not collapse.
        self.assertIn("sidebar.translatesAutoresizingMaskIntoConstraints = false", generated)
        self.assertIn("workspace.alignment = .leading", generated)
        self.assertIn("column.alignment = .leading", generated)
        self.assertNotIn(".alignment = .width", generated)
        self.assertIn("result.alignment = axis == .vertical ? .leading : .centerY", generated)
        self.assertIn("func addPage(_ page: NSView)", generated)
        self.assertIn("page.widthAnchor.constraint(equalTo: workspace.widthAnchor)", generated)
        self.assertIn("row.widthAnchor.constraint(equalTo: wrapper.widthAnchor)", generated)
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
