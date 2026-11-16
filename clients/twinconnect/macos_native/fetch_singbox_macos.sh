#!/usr/bin/env bash
# Official sing-box macOS executables for independent native-engine preflight.
# No VPN is started and no client credentials are handled by this script.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
version="1.14.4"
base="https://github.com/SagerNet/sing-box/releases/download/v${version}"
dest="$root/macos_native/build/singbox"
mkdir -p "$dest"
for arch in arm64 amd64; do
  case "$arch" in
    arm64) digest="0d8c7f5ed5d587b0f1a5e9772a708ec3bfa4ac4c9329604b01d8d9c2ba406838";;
    amd64) digest="eae86b9b033bba50b7c44ab719e4bfac0aca05efd28483390ed3aa510f32db25";;
  esac
  archive="$dest/sing-box-${version}-darwin-${arch}.tar.gz"
  curl --fail --location --retry 3 --silent --show-error \
    "$base/sing-box-${version}-darwin-${arch}.tar.gz" -o "$archive"
  printf '%s  %s\n' "$digest" "$archive" | shasum -a 256 -c -
  mkdir -p "$dest/$arch"
  tar -xzf "$archive" -C "$dest/$arch" --strip-components=1 \
    "sing-box-${version}-darwin-${arch}/sing-box"
  test -s "$dest/$arch/sing-box"
  chmod +x "$dest/$arch/sing-box"
  file "$dest/$arch/sing-box"
done
"$dest/arm64/sing-box" version
