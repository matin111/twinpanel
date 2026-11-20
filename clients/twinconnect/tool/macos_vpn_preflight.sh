#!/bin/bash
# TwinConnect macOS Packet Tunnel signing and backend preflight.
# Read-only: never creates certificates, changes provisioning, or modifies Xcode.
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0
check() { if eval "$2"; then printf 'PASS %s\n' "$1"; else printf 'FAIL %s\n' "$1"; fail=1; fi; }
printf '%s\n' 'TwinConnect macOS PacketTunnel readiness preflight'
check 'Xcode command-line tools' 'xcode-select -p >/dev/null 2>&1'
host_version="$(sw_vers -productVersion 2>/dev/null || printf unknown)"
host_major="$(printf '%s' "$host_version" | cut -d. -f1)"
printf 'INFO host macOS version: %s\n' "$host_version"
if [ "$host_major" -ge 11 ] 2>/dev/null; then
  printf '%s\n' 'PASS host supports the macOS 11+ PacketTunnel deployment target'
else
  printf '%s\n' 'FAIL host macOS is below the PacketTunnel deployment target (11.0)'
  fail=1
fi
check 'macOS Flutter project' 'test -d macos/Runner.xcodeproj'
check 'PacketTunnel Xcode target' 'grep -q "PacketTunnel" macos/Runner.xcodeproj/project.pbxproj'
check 'Network Extension requested by extension' '/usr/libexec/PlistBuddy -c "Print :com.apple.developer.networking.networkextension:0" macos_native/PacketTunnel.entitlements 2>/dev/null | grep -qx "packet-tunnel-provider"'
check 'PacketTunnel extension definition' '/usr/libexec/PlistBuddy -c "Print :NSExtension:NSExtensionPointIdentifier" macos_native/PacketTunnel-Info.plist 2>/dev/null | grep -qx "com.apple.networkextension.packet-tunnel"'
if security find-identity -v -p codesigning 2>/dev/null | grep -Eq '[0-9]+ valid identities found'; then
  identity_count="$(security find-identity -v -p codesigning 2>/dev/null | grep -E '[0-9]+ valid identities found' | sed -E 's/^[[:space:]]*([0-9]+).*/\1/')"
else identity_count=0; fi
if [ "${identity_count:-0}" -gt 0 ] 2>/dev/null; then
  printf 'INFO %s available signing identity/identities; Apple Network Extension provisioning not verified\n' "$identity_count"
else
  printf '%s\n' 'FAIL no usable code signing identity in keychain'
  fail=1
fi
if grep -q 'TWINCONNECT_SIGNED_WIREGUARD' macos_native/TwinConnectMacOSVPNBridge.swift; then
  printf '%s\n' 'INFO WireGuard startup is gated behind signed PacketTunnel entitlement verification'
fi
if ! grep -A1 'TwinConnectWireGuardBackendLinked' macos_native/PacketTunnel-Info.plist | grep -q '<true/>'; then
  printf '%s\n' 'FAIL signed WireGuard backend marker is not enabled in PacketTunnel bundle'
  fail=1
fi
found_extension="$(find "$HOME/Library/Developer/Xcode/DerivedData" -path '*/Build/Products/Debug/*.app/Contents/PlugIns/PacketTunnel.appex/Contents/MacOS/PacketTunnel' -type f -print -quit 2>/dev/null)"
if [ -n "$found_extension" ]; then
  if nm -g "$found_extension" 2>/dev/null | grep -q '_wgTurnOn'; then
    printf '%s\n' 'PASS built PacketTunnel includes native WireGuard Go symbols'
  else
    printf '%s\n' 'FAIL built PacketTunnel does not include WireGuard Go symbols'
    fail=1
  fi
else
  printf '%s\n' 'INFO built PacketTunnel executable was not found in Xcode DerivedData'
fi
if [ -d macos/Flutter/ephemeral ]; then
  printf '%s\n' 'INFO Flutter macOS generated files are present'
fi
printf '%s\n' 'INFO an unsigned build can compile but cannot provide a working PacketTunnel VPN'
printf '%s\n' 'INFO a valid certificate alone does not prove Network Extension entitlement approval'
if [ "$fail" -ne 0 ]; then
  printf '%s\n' 'RESULT not ready for signed live VPN tests'
  exit 1
fi
printf '%s\n' 'RESULT preliminary checks passed; verify both signed entitlements and actual packet forwarding'
