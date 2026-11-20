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
        self.assertIn(
            "self.contentViewController = TwinConnectMacOSMetalFallback()",
            generated
        )
        self.assertIn("VPN unavailable: a signed Apple Network Extension is required", generated)
        self.assertIn("TWINCONNECT_MACOS_NATIVE_DIRECTORY_V1", generated)
        self.assertIn("TWINCONNECT_MACOS_NATIVE_DASHBOARD_V1", generated)
        self.assertIn("v1/central-app/public/login", generated)
        self.assertIn("v1/central-app/session/servers", generated)
        self.assertIn("v1/central-app/session/protocols", generated)
        self.assertIn("v1/central-app/session/plan", generated)
        self.assertIn("Quick connect", generated)
        self.assertIn("Locations", generated)
        self.assertIn("Settings", generated)
        self.assertIn("Account", generated)
        self.assertIn("TwinNativePowerRing", generated)
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
