#!/bin/bash
# Real WireGuard cryptography and loopback UDP tests with virtual packet I/O.
# No privileged tunnel, route, firewall, Apple signing, or production credentials.
set -euo pipefail
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
cd "$(dirname "$0")/.."
root="$PWD"
source="$HOME/twinpanel/clients/twinconnect/macos_native/build/wireguard-apple"
if [ "$#" -gt 0 ]; then source="$1"; fi
revision=2fec12a6e1f6e3460b6ee483aa00ad29cddadab1
test "$(git -C "$source" rev-parse HEAD)" = "$revision" || {
  echo 'ERROR: unexpected WireGuard Apple source revision' >&2
  exit 1
}
vendor="$root/.dart_tool/ios-wireguard-lab/$revision"
mkdir -p "$vendor"
git -C "$source" archive "$revision" | tar -xf - -C "$vendor"
cd "$vendor/Sources/WireGuardKitGo"
echo "WIREGUARD_SOURCE=$revision"
# Upstream TestTwoDevicePing uses two ChannelTUNs, real UDP sockets,
# actual WireGuard peers and byte-for-byte bidirectional IP packet verification.
GOPROXY=off GOSUMDB=off go test -mod=readonly -count=1 -timeout=45s \
  -run '^TestTwoDevicePing$' -v golang.zx2c4.com/wireguard/device
echo 'PASS: real WireGuard peer-to-peer packets over local UDP; virtual TUN only'
