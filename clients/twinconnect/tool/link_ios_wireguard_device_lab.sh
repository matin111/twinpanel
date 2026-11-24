#!/bin/bash
# Compile and link the real upstream WireGuardKit branch into an unsigned
# iOS device extension. Not a provisioned/embedded or runtime-verified VPN.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
REV=2fec12a6e1f6e3460b6ee483aa00ad29cddadab1
V="$ROOT/.dart_tool/ios-wireguard-lab/$REV/Sources"
OUT="$ROOT/build/ios-wireguard-lab/iphoneos"
test -s "$OUT/libwg-go.a" || bash tool/build_ios_wireguard_archive_lab.sh "$@"
test -d "$V/WireGuardKit"
SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
T=arm64-apple-ios15.0
mkdir -p "$OUT/kit" "$OUT/PacketTunnel.appex"
for src in "$V"/WireGuardKitC/*.c; do
  xcrun --sdk iphoneos clang -target "$T" -isysroot "$SDK" -c "$src" -o "$OUT/kit/$(basename "$src" .c).o"
done
xcrun --sdk iphoneos swiftc -target "$T" -sdk "$SDK" -D SWIFT_PACKAGE \
  -I "$V/WireGuardKitC" -I "$V/WireGuardKitGo" \
  -emit-library -static -emit-module -module-name WireGuardKit \
  -emit-module-path "$OUT/kit/WireGuardKit.swiftmodule" \
  "$V"/WireGuardKit/*.swift -o "$OUT/kit/libWireGuardKit.a"
for f in TunnelConfiguration+WgQuickConfig.swift String+ArrayConversion.swift; do
  { echo 'import WireGuardKit'; cat "$V/Shared/Model/$f"; } > "$OUT/kit/$f"
done
xcrun --sdk iphoneos swiftc -target "$T" -sdk "$SDK" -module-name PacketTunnel \
  -application-extension -I "$OUT/kit" -I "$V/WireGuardKitC" -I "$V/WireGuardKitGo" \
  -L "$OUT" -L "$OUT/kit" -lWireGuardKit -lwg-go \
  -framework NetworkExtension -framework Network -framework Security -framework Foundation \
  -Xlinker -e -Xlinker _NSExtensionMain -Xlinker -no_adhoc_codesign \
  ios_native/PacketTunnelProvider.swift ios_native/TwinConnectWireGuardEngine.swift \
  "$OUT/kit/TunnelConfiguration+WgQuickConfig.swift" "$OUT/kit/String+ArrayConversion.swift" \
  "$OUT/kit/key.o" "$OUT/kit/x25519.o" -o "$OUT/PacketTunnel.appex/PacketTunnel"
# Generate lab-only metadata; keep the shipping capability marker false.
python3 - "$OUT/PacketTunnel.appex/Info.plist" <<'PY'
import plistlib, sys
with open("ios_native/PacketTunnel-Info.plist", "rb") as f:
    p = plistlib.load(f)
p.update(CFBundleDevelopmentRegion="en", CFBundleExecutable="PacketTunnel",
         CFBundleIdentifier="com.twinpanel.twinconnect.PacketTunnel",
         CFBundleShortVersionString="0.1.0", CFBundleVersion="1",
         TwinConnectWireGuardBackendLinked=False)
p["NSExtension"]["NSExtensionPrincipalClass"] = "PacketTunnel.PacketTunnelProvider"
with open(sys.argv[1], "wb") as f:
    plistlib.dump(p, f)
PY
xcrun lipo "$OUT/PacketTunnel.appex/PacketTunnel" -verify_arch arm64
xcrun nm "$OUT/PacketTunnel.appex/PacketTunnel" > "$OUT/kit/linked-symbols.txt"
for symbol in wgTurnOn wgTurnOff wgGetConfig; do
  grep -E " [Tt] _$symbol$" "$OUT/kit/linked-symbols.txt"
done
xcrun vtool -show-build "$OUT/PacketTunnel.appex/PacketTunnel"
echo 'PASS: real WireGuardKit linked to unsigned ARM64 PacketTunnel extension; device runtime NOT verified'
