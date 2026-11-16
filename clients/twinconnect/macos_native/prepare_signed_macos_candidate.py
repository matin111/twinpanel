#!/usr/bin/env python3
"""Explicit, local-only preparation of a developer-signed macOS VPN test.

Prerequisites: generated Flutter macOS Runner, PacketTunnel target, and
Libbox.xcframework linked and embedded. Never run for unsigned CI previews.
The script provisions NO Apple certificates and cannot enable VPN by itself.
"""
from __future__ import annotations

import os
import plistlib
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
team = os.environ.get("TWINCONNECT_APPLE_TEAM_ID", "")
opt_in = os.environ.get("TWINCONNECT_ENABLE_SIGNED_LIBBOX_TEST", "")
if not re.fullmatch(r"[A-Z0-9]{10}", team) or opt_in != "YES":
    raise SystemExit(
        "SIGNED_TEST_NOT_AUTHORIZED: set a real Apple Team ID and "
        "TWINCONNECT_ENABLE_SIGNED_LIBBOX_TEST=YES"
    )

project = root / "macos/Runner.xcodeproj/project.pbxproj"
framework = root / "macos_native/build/libbox/Libbox.xcframework/Info.plist"
if not project.is_file() or not framework.is_file():
    raise SystemExit("SIGNED_TEST_MISSING_XCODE_OR_LIBBOX_FRAMEWORK")
pbx = project.read_text()
if "PacketTunnel" not in pbx or "Libbox.framework" not in pbx:
    raise SystemExit("SIGNED_TEST_LIBBOX_NOT_LINKED_TO_PACKET_TUNNEL")

group = f"{team}.com.twinpanel.twinconnect.shared"

def update_entitlement(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"SIGNED_TEST_ENTITLEMENT_MISSING: {path.name}")
    with path.open("rb") as source:
        settings = plistlib.load(source)
    settings["com.apple.security.app-sandbox"] = True
    settings["com.apple.security.network.client"] = True
    settings["com.apple.developer.networking.networkextension"] = [
        "packet-tunnel-provider"
    ]
    settings["keychain-access-groups"] = [group]
    with path.open("wb") as destination:
        plistlib.dump(settings, destination, sort_keys=True)

for filename in ("Release.entitlements", "DebugProfile.entitlements"):
    update_entitlement(root / "macos/Runner" / filename)
update_entitlement(root / "macos_native/PacketTunnel.entitlements")

app_info = root / "macos/Runner/Info.plist"
if not app_info.is_file():
    raise SystemExit("SIGNED_TEST_RUNNER_INFO_MISSING")
with app_info.open("rb") as source:
    app_settings = plistlib.load(source)
app_settings["TwinConnectKeychainAccessGroup"] = group
with app_info.open("wb") as destination:
    plistlib.dump(app_settings, destination, sort_keys=False)

extension_info = root / "macos_native/PacketTunnel-Info.plist"
with extension_info.open("rb") as source:
    extension_settings = plistlib.load(source)
extension_settings["TwinConnectProtocolBackendLinked"] = True
with extension_info.open("wb") as destination:
    plistlib.dump(extension_settings, destination, sort_keys=False)

# The signed test candidate also needs Xcode's Swift build condition:
# SWIFT_ACTIVE_COMPILATION_CONDITIONS='TWINCONNECT_SIGNED_LIBBOX'
# It is intentionally NOT installed in unsigned default builds.
print("SIGNED_LIBBOX_TEST_CONFIGURED")
print(f"TEAM_ID={team}")
print(f"KEYCHAIN_GROUP={group}")
print("APPLE_PROVISIONING_NETWORK_EXTENSION_APPROVAL_REQUIRED")
print("REAL_EGRESS_HANDSHAKE_DNS_KILLSWITCH_NOT_VERIFIED")
