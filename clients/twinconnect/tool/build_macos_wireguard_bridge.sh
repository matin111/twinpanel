#!/bin/bash
# Build the official WireGuard Go static bridge for the current macOS host architecture.
# This does NOT sign or enable the VPN; it only builds a library required by WireGuardKit.
set -euo pipefail
cd "$(dirname "$0")/.."
root="$(pwd)"
source_dir="$root/.dart_tool/twinconnect-wireguard-apple"
out_dir="$root/.dart_tool/twinconnect-wireguard-build"
if [ ! -f "$source_dir/Sources/WireGuardKitGo/Makefile" ]; then
  echo "ERROR upstream source is missing. Run: bash tool/prepare_macos_wireguard_sources.sh" >&2
  exit 1
fi
if ! command -v go >/dev/null 2>&1 || ! command -v make >/dev/null 2>&1; then
  echo "ERROR Go and make are required." >&2
  exit 1
fi
arch="$(uname -m)"
case "$arch" in
  x86_64|arm64) ;;
  *) echo "ERROR unsupported host architecture: $arch" >&2; exit 1 ;;
esac
sdk="$(xcrun --sdk macosx --show-sdk-path)"
mkdir -p "$out_dir/lib" "$out_dir/tmp"
echo "Building WireGuard Go bridge for $arch on macOS..."
echo "Upstream source: $(git -C "$source_dir" rev-parse HEAD)"
echo "Go: $(go version)"
make -C "$source_dir/Sources/WireGuardKitGo" \
  ARCHS="$arch" PLATFORM_NAME=macosx SDKROOT="$sdk" \
  CONFIGURATION_BUILD_DIR="$out_dir/lib" \
  CONFIGURATION_TEMP_DIR="$out_dir/tmp" \
  DESTDIR="$out_dir/lib" build version-header
test -s "$out_dir/lib/libwg-go.a"
echo "SUCCESS static WireGuard Go bridge: $out_dir/lib/libwg-go.a"
file "$out_dir/lib/libwg-go.a"
echo 'NEXT: link WireGuardKit and libwg-go.a to PacketTunnel; this script does not alter Xcode or signing.'
