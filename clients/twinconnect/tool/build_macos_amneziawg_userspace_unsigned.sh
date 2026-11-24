#!/usr/bin/env bash
# Build pinned official AWG engine/tools. No sudo, VPN, DNS or route changes.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin ]] || { echo "AWG_MACOS_REQUIRED"; exit 2; }
case "$(uname -m)" in
  x86_64) arch=amd64;;
  arm64) arch=arm64;;
  *) echo "AWG_ARCH_UNSUPPORTED"; exit 2;;
esac
root="$PWD"
go_binary="$(command -v go || true)"
[[ -n "$go_binary" ]] || go_binary=/usr/local/bin/go
[[ -x "$go_binary" ]] || { echo "AWG_GO_TOOLCHAIN_MISSING"; exit 2; }
stage="$(mktemp -d -t twinconnect-awg-build)"
trap 'rm -rf -- "$stage"' EXIT
git clone --quiet --depth 1 --branch v3.1.20260828 https://github.com/amnezia-vpn/amneziawg-go.git "$stage/go"
git clone --quiet --depth 1 --branch v3.1.20260812 https://github.com/amnezia-vpn/amneziawg-tools.git "$stage/tools"
[[ "$(git -C "$stage/go" rev-parse HEAD)" == b5928efb6ca19f0153958460c3d141f04abc5c2e ]]
[[ "$(git -C "$stage/tools" rev-parse HEAD)" == ee0f0a9aa34ff0a0da4b3433b9512781cfe02843 ]]
(cd "$stage/go" && GOTOOLCHAIN=local "$go_binary" build -mod=readonly -trimpath -o "$stage/amneziawg-go" .)
(cd "$stage/tools/src" && make wg)
"$stage/amneziawg-go" --version | grep -q "Userspace AmneziaWG daemon for darwin-$arch"
"$stage/tools/src/wg" --version | grep -q '^amneziawg-tools'
out="$root/macos_native/build/amneziawg/$arch"
[[ ! -L "$out" && ! -L "$out/amneziawg-go" && ! -L "$out/awg" ]]
mkdir -p "$out"
install -m 0755 "$stage/amneziawg-go" "$out/amneziawg-go"
install -m 0755 "$stage/tools/src/wg" "$out/awg"
echo "AMNEZIAWG_ENGINE_PAIR_BUILT_NO_NETWORK_CHANGES"
