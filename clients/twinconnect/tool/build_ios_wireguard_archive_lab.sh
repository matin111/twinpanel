#!/bin/bash
# Cross-compile the pinned WireGuard Go library; unsigned laboratory only.
# The old Go runtime patch is not validated against modern Go.
# A compiled archive is not a verified production engine or iOS VPN.
set -euo pipefail
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
cd "$(dirname "$0")/.."
root="$PWD"
source="$HOME/twinpanel/clients/twinconnect/macos_native/build/wireguard-apple"
if [ "$#" -gt 0 ]; then source="$1"; fi
revision=2fec12a6e1f6e3460b6ee483aa00ad29cddadab1
test "$(git -C "$source" rev-parse HEAD)" = "$revision" || exit 1
vendor="$root/.dart_tool/ios-wireguard-lab/$revision"
mkdir -p "$vendor" "$root/build/ios-wireguard-lab/iphoneos"
git -C "$source" archive "$revision" | tar -xf - -C "$vendor"
sdk="$(xcrun --sdk iphoneos --show-sdk-path)"
clang="$(xcrun --sdk iphoneos --find clang)"
cd "$vendor/Sources/WireGuardKitGo"
export GOOS=ios GOARCH=arm64 CGO_ENABLED=1 CC="$clang"
export CGO_CFLAGS="-isysroot $sdk -arch arm64 -miphoneos-version-min=15.0"
export CGO_LDFLAGS="$CGO_CFLAGS"
export GOPROXY=off GOSUMDB=off
out="$root/build/ios-wireguard-lab/iphoneos/libwg-go.a"
go build -mod=readonly -trimpath -buildmode=c-archive -o "$out" .
xcrun lipo -info "$out"
xcrun nm -gU "$out" > "$root/build/ios-wireguard-lab/iphoneos/symbols.txt"
grep -E ' [Tt] _wg(TurnOn|TurnOff|GetConfig)$' "$root/build/ios-wireguard-lab/iphoneos/symbols.txt"
echo 'PASS: iOS ARM64 WireGuard Go archive compiled, NOT runtime verified'
