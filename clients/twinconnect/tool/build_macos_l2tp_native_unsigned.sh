#!/usr/bin/env bash
# Offline native L2TP service setup helper. No Apple codesign/NetworkExtension.
# The build does NOT create an L2TP network service or change any route/DNS.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin ]] || { echo L2TP_MACOS_REQUIRED >&2; exit 2; }
case "$(uname -m)" in
  x86_64) arch=amd64;;
  arm64) arch=arm64;;
  *) echo L2TP_ARCH_UNSUPPORTED >&2; exit 2;;
esac
source_file=macos_native/TwinConnectL2TPNativeService.m
[[ -f "$source_file" && ! -L "$source_file" ]] || {
  echo L2TP_SOURCE_UNTRUSTED >&2; exit 2
}
out="macos_native/build/l2tp/$arch"
[[ ! -L "$out" && ! -L "$out/twinconnect-l2tp-native" ]] || {
  echo L2TP_OUTPUT_UNSAFE >&2; exit 2
}
mkdir -p "$out"
stage="$(mktemp -d -t twinconnect-l2tp-unsigned)"
trap 'rm -rf -- "$stage"' EXIT
xcrun clang -fobjc-arc -Wall -Wextra -Werror \
  -framework Foundation -framework SystemConfiguration \
  -framework CoreFoundation \
  "$source_file" -o "$stage/twinconnect-l2tp-native"
"$stage/twinconnect-l2tp-native" capabilities |
  grep -q '"connected":false' || {
    echo L2TP_READONLY_CAPABILITY_CHECK_FAILED >&2; exit 3
  }
install -m 0755 "$stage/twinconnect-l2tp-native" \
  "$out/twinconnect-l2tp-native"
echo "L2TP_NATIVE_UNSIGNED_COMPILED: $out/twinconnect-l2tp-native"
echo "L2TP_SERVICE_NOT_MODIFIED; VPN_NOT_CONNECTED"
