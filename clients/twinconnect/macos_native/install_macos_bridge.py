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
if not window.is_file() or not native.is_file() or not control.is_file() or not libbox_control.is_file():
    raise SystemExit("macOS Flutter project / native bridge not found")

content = window.read_text(encoding="utf-8")
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
