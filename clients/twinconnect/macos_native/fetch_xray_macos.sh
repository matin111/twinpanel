#!/usr/bin/env bash
# Official Xray-core transport engine preflight for both macOS architectures.
# Pinned SHA-256 protects the downloaded release archives.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
version="26.11.9"
base="https://github.com/XTLS/Xray-core/releases/download/v${version}"
dest="$root/macos_native/build/xray"
mkdir -p "$dest"
for arch in arm64 amd64; do
  case "$arch" in
    arm64)
      archive_name="Xray-macos-arm64-v8a.zip"
      digest="233f0c66681cd0726f81a6b2b6ed6a5710869e312047b522e46ed53035bebd26"
      ;;
    amd64)
      archive_name="Xray-macos-64.zip"
      digest="488963e676e06f5e48547f9dd38116aaca8de4234959b4272ae8f284e658dfd0"
      ;;
  esac
  archive="$dest/$archive_name"
  curl --fail --location --retry 3 --silent --show-error "$base/$archive_name" -o "$archive"
  printf '%s  %s\n' "$digest" "$archive" | shasum -a 256 -c -
  mkdir -p "$dest/$arch"
  unzip -j -q -o "$archive" xray -d "$dest/$arch"
  test -s "$dest/$arch/xray"
  chmod +x "$dest/$arch/xray"
  file "$dest/$arch/xray"
done
"$dest/arm64/xray" version
