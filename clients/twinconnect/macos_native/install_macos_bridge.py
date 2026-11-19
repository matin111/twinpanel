"""Install the macOS capability boundary in generated Flutter scaffolding.

Run after `flutter create --platforms=macos`. It only changes the generated
macOS project, never Windows/iOS sources or existing subscription data.
"""
from __future__ import annotations

from pathlib import Path
import plistlib

root = Path(__file__).resolve().parents[1]
window = root / "macos/Runner/MainFlutterWindow.swift"
native = root / "macos_native/TwinConnectMacOSVPNBridge.swift"
control = root / "macos_native/TwinConnectMacOSVPNControl.swift"
libbox_control = root / "macos_native/TwinConnectMacOSLibboxControl.swift"
mieru_control = root / "macos_native/TwinConnectMacOSMieruControl.swift"
metal_fallback = root / "macos_native/TwinConnectMacOSMetalFallback.swift"
if not window.is_file() or not native.is_file() or not control.is_file() or not libbox_control.is_file() or not mieru_control.is_file() or not metal_fallback.is_file():
    raise SystemExit("macOS Flutter project / native bridge not found")

content = window.read_text(encoding="utf-8")
# A FlutterViewController creates its Metal-backed view in the window startup
# path. Fail gracefully *before* constructing it on Metal-less cloud Macs.
# --enable-software-rendering is not an alternative to a missing macOS
# MTLDevice/MTLCommandQueue in the stock Flutter desktop embedder.
import_anchor = "import FlutterMacOS"
if import_anchor not in content:
    raise SystemExit("Unexpected Flutter macOS MainFlutterWindow imports")
if "import Metal" not in content:
    content = content.replace(import_anchor, import_anchor + "\\nimport Metal", 1)
startup_anchor = "let flutterViewController = FlutterViewController()"
startup_marker = "// TWINCONNECT_MACOS_METAL_PREFLIGHT_V1"
if content.count(startup_anchor) != 1:
    raise SystemExit("Unexpected macOS Flutter window startup; aborting")
if startup_marker not in content:
    guard = (
        "    " + startup_marker + "\\n"
        "    guard let metal = MTLCreateSystemDefaultDevice(),\\n"
        "          metal.makeCommandQueue() != nil else {\\n"
        "      let originalFrame = self.frame\\n"
        "      self.contentViewController = TwinConnectMacOSMetalFallback()\\n"
        "      self.setFrame(originalFrame, display: true)\\n"
        "      super.awakeFromNib()\\n"
        "      return\\n"
        "    }\\n"
    )
    content = content.replace(startup_anchor, guard + "    " + startup_anchor, 1)
anchor = "RegisterGeneratedPlugins(registry: flutterViewController)"
registration = (
    "\n    TwinConnectMacOSVPNBridge.register("
    "binaryMessenger: flutterViewController.engine.binaryMessenger)"
)
if content.count(anchor) != 1:
    raise SystemExit("Unexpected macOS Flutter window template; aborting")
if "TwinConnectMacOSVPNBridge.register(" not in content:
    content = content.replace(anchor, anchor + registration)
marker = "// TWINCONNECT_MACOS_NATIVE_BRIDGE_V1"
if marker not in content:
    content = content.rstrip() + "\n\n" + marker + "\n" + native.read_text(encoding="utf-8")
control_marker = "// TWINCONNECT_MACOS_CONTROL_V1"
if control_marker not in content:
    content = content.rstrip() + "\n\n" + control_marker + "\n" + control.read_text(encoding="utf-8")
libbox_marker = "// TWINCONNECT_MACOS_LIBBOX_CONTROL_V1"
if libbox_marker not in content:
    content = content.rstrip() + "\n\n" + libbox_marker + "\n" + libbox_control.read_text(encoding="utf-8")
mieru_marker = "// TWINCONNECT_MACOS_MIERU_CONTROL_V1"
if mieru_marker not in content:
    content = content.rstrip() + "\n\n" + mieru_marker + "\n" + mieru_control.read_text(encoding="utf-8")
fallback_marker = "// TWINCONNECT_MACOS_METAL_FALLBACK_V1"
if fallback_marker not in content:
    content = content.rstrip() + "\\n\\n" + fallback_marker + "\\n" + metal_fallback.read_text(encoding="utf-8")
window.write_text(content, encoding="utf-8")

# App sandbox requires a client-network entitlement for license discovery,
# panel login, subscription requests, and HTTPS status checks.
for name in ("DebugProfile.entitlements", "Release.entitlements"):
    path = root / "macos/Runner" / name
    if not path.is_file():
        raise SystemExit(f"macOS entitlements not found: {path}")
    with path.open("rb") as f:
        entitlements = plistlib.load(f)
    entitlements["com.apple.security.network.client"] = True
    # Do NOT fabricate Network Extension entitlements: a real team-signed
    # provider extension is required to establish a production VPN.
    with path.open("wb") as f:
        plistlib.dump(entitlements, f, sort_keys=True)
print("Mac native bridge installed; HTTPS enabled; tunnel engine NOT installed")
