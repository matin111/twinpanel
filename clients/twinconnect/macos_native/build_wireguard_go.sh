#!/usr/bin/env bash
# Build pinned upstream wireguard-go bridge for macOS arm64 in CI.
# This does not grant any Network Extension entitlement.
set -euo pipefail
cd "$(dirname "$0")/.."
client_root="$PWD"
checkout="${1:?Pass the Xcode-resolved wireguard-apple checkout directory}"
test -f "$checkout/Sources/WireGuardKitGo/Makefile"
command -v go
command -v xcrun
mkdir -p "$client_root/macos_native/build/wireguard"
make -C "$checkout/Sources/WireGuardKitGo" build \
  ARCHS=arm64 PLATFORM_NAME=macosx \
  CONFIGURATION_BUILD_DIR="$client_root/macos_native/build/wireguard" \
  CONFIGURATION_TEMP_DIR="$client_root/macos_native/build/wireguard-temp"
test -s "$client_root/macos_native/build/wireguard/libwg-go.a"
file "$client_root/macos_native/build/wireguard/libwg-go.a"
