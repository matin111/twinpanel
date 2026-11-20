#!/bin/bash
# Prepare upstream WireGuardKit sources for the macOS PacketTunnel integration.
# This script only downloads sources; it does not modify Xcode targets or signing.
set -euo pipefail
cd "$(dirname "$0")/.."
root="$(pwd)"
vendor="$root/.dart_tool/twinconnect-wireguard-apple"
if ! command -v git >/dev/null 2>&1; then echo 'ERROR git is required'; exit 1; fi
if ! command -v go >/dev/null 2>&1; then
  echo 'ERROR Go is required for the WireGuardKitGo bridge (brew install go)'
  exit 1
fi
if [ ! -d "$vendor/.git" ]; then
  echo 'Downloading official WireGuard Apple sources into untracked build cache...'
  git clone --depth 1 https://github.com/WireGuard/wireguard-apple.git "$vendor"
fi
if [ ! -f "$vendor/Package.swift" ] || [ ! -f "$vendor/Sources/WireGuardKitGo/Makefile" ]; then
  echo 'ERROR upstream WireGuardKit sources are incomplete'; exit 1
fi
echo "SOURCE_DIR=$vendor"
echo "SOURCE_COMMIT=$(git -C "$vendor" rev-parse HEAD)"
echo "GO_VERSION=$(go version)"
echo 'WireGuard sources downloaded. Xcode package product and Go bridge are NOT linked yet.'
echo 'Follow the upstream WireGuardKit integration procedure:'
echo 'https://github.com/WireGuard/wireguard-apple#wireguardkit-integration'
echo 'The official integration requires an Xcode External Build System target for WireGuardGoBridge and a WireGuardKit package dependency on PacketTunnel.'
