#!/usr/bin/env bash
# Build upstream WireGuard userspace daemon WITHOUT Apple signing.
# Never starts VPN or changes routes, DNS, system settings or active sessions.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin ]] || { echo "WIREGUARD_MACOS_REQUIRED" >&2; exit 2; }
case "$(uname -m)" in
  x86_64) arch=amd64;;
  arm64) arch=arm64;;
  *) echo "WIREGUARD_UNSUPPORTED_ARCH" >&2; exit 2;;
esac
upstream="v0.0.0-20230209153558-1e2c3e5a3c14"
source_dir="$HOME/go/pkg/mod/golang.zx2c4.com/wireguard@$upstream"
[[ -f "$source_dir/go.mod" && -f "$source_dir/go.sum" &&
   -f "$source_dir/main.go" && ! -L "$source_dir" ]] || {
  echo "WIREGUARD_PINNED_SOURCE_MISSING" >&2; exit 3;
}
go_binary="/usr/local/bin/go"
[[ -x "$go_binary" ]] || {
  echo "WIREGUARD_GO_TOOLCHAIN_MISSING" >&2; exit 3;
}
temp="$(mktemp -d -t twinconnect-wireguard-unsigned)"
trap 'rm -rf "$temp"' EXIT
cp "$source_dir/go.mod" "$temp/pinned.mod"
cp "$source_dir/go.sum" "$temp/pinned.sum"
chmod u+w "$temp/pinned.mod" "$temp/pinned.sum"
# The bundled WireGuardKitGo has these dependencies cached. The upstream
# standalone CLI module otherwise requests older, unavailable versions.
"$go_binary" mod edit -modfile="$temp/pinned.mod" \
  -require=golang.org/x/crypto@v0.6.0 \
  -require=golang.org/x/net@v0.6.0 \
  -require=golang.org/x/sys@v0.5.0 \
  -droprequire=gvisor.dev/gvisor \
  -droprequire=github.com/google/btree \
  -droprequire=golang.org/x/time
(
  cd "$source_dir"
  GOPROXY=off GOSUMDB=off "$go_binary" build \
    -mod=mod -modfile="$temp/pinned.mod" -trimpath \
    -o "$temp/wireguard-go" .
)
[[ -s "$temp/wireguard-go" && -x "$temp/wireguard-go" ]] || {
  echo "WIREGUARD_UNSIGNED_BUILD_FAILED" >&2; exit 3;
}
"$temp/wireguard-go" --version | grep -Fq "Userspace WireGuard daemon for darwin-$arch" || {
  echo "WIREGUARD_UNSIGNED_VERSION_INVALID" >&2; exit 3;
}
out="macos_native/build/wireguard-userspace/$arch"
[[ ! -L "$out" && ! -L "$out/wireguard-go" ]] || {
  echo "WIREGUARD_UNSAFE_OUTPUT_PATH" >&2; exit 3;
}
mkdir -p "$out"
install -m 0755 "$temp/wireguard-go" "$out/wireguard-go"
echo "WIREGUARD_UNSIGNED_DAEMON_BUILT: $out/wireguard-go"
echo "WIREGUARD_USERSPACE_ONLY; NO_SYSTEM_ROUTE_OR_SIGNING_CONFIGURED"
