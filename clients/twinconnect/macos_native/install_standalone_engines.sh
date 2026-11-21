#!/usr/bin/env bash
# Install pinned, SHA-256 checked official macOS proxy engines for this host.
# Does not start a VPN, change routing, DNS, firewall or require sudo.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
arch="$(uname -m)"
case "$arch" in
  x86_64) arch=amd64 ;;
  arm64) arch=arm64 ;;
  *) echo "Unsupported macOS architecture: $arch" >&2; exit 1 ;;
esac

for cmd in curl shasum tar unzip mktemp; do
  command -v "$cmd" >/dev/null || { echo "Missing: $cmd" >&2; exit 1; }
done

work="$(mktemp -d "${TMPDIR:-/tmp}/twinconnect-engines.XXXXXXXX")"
trap 'rm -rf "$work"' EXIT
dest="$root/macos_native/build"

verify() {
  local expected="$1" archive="$2"
  printf '%s  %s\n' "$expected" "$archive" | shasum -a 256 -c -
}
install_one() {
  local from="$1" target="$2"
  mkdir -p "$(dirname "$target")"
  install -m 755 "$from" "$target"
  test -x "$target"
}

sing_version=1.14.4
case "$arch" in
  amd64) sing_sha=eae86b9b033bba50b7c44ab719e4bfac0aca05efd28483390ed3aa510f32db25 ;;
  arm64) sing_sha=0d8c7f5ed5d587b0f1a5e9772a708ec3bfa4ac4c9329604b01d8d9c2ba406838 ;;
esac
sing_name="sing-box-${sing_version}-darwin-${arch}.tar.gz"
curl -fL --retry 3 --connect-timeout 15 --max-time 180 \
  "https://github.com/SagerNet/sing-box/releases/download/v${sing_version}/${sing_name}" \
  -o "$work/$sing_name"
verify "$sing_sha" "$work/$sing_name"
tar -xzf "$work/$sing_name" -C "$work" \
  "sing-box-${sing_version}-darwin-${arch}/sing-box"
install_one "$work/sing-box-${sing_version}-darwin-${arch}/sing-box" \
  "$dest/singbox/$arch/sing-box"

xray_version=26.11.9
case "$arch" in
  amd64)
    xray_name=Xray-macos-64.zip
    xray_sha=488963e676e06f5e48547f9dd38116aaca8de4234959b4272ae8f284e658dfd0
    ;;
  arm64)
    xray_name=Xray-macos-arm64-v8a.zip
    xray_sha=233f0c66681cd0726f81a6b2b6ed6a5710869e312047b522e46ed53035bebd26
    ;;
esac
curl -fL --retry 3 --connect-timeout 15 --max-time 180 \
  "https://github.com/XTLS/Xray-core/releases/download/v${xray_version}/${xray_name}" \
  -o "$work/$xray_name"
verify "$xray_sha" "$work/$xray_name"
mkdir -p "$work/xray"
unzip -j -q "$work/$xray_name" xray -d "$work/xray"
install_one "$work/xray/xray" "$dest/xray/$arch/xray"

echo "Installed official, digest-verified engines for macOS $arch:"
"$dest/singbox/$arch/sing-box" version
"$dest/xray/$arch/xray" version
echo 'No network routes or system VPN settings have been changed.'
