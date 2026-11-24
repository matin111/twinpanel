#!/usr/bin/env bash
# Hash-pinned official CLI for local SOCKS compatibility work only.
# No Apple Developer certificate, root helper, VPN route, or DNS changes.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin && "$(uname -m)" == "x86_64" ]] || {
  echo "TRUSTTUNNEL_REQUIRES_DARWIN_AMD64" >&2; exit 2;
}
version="1.3.0"
sha="2896dd6e0ddeed6b379c5a7be72b26ba1bbc7ad830182ebc2d1f880965925186"
archive="trusttunnel_client-v$version-macos-universal.tar.gz"
url="https://github.com/TrustTunnel/TrustTunnelClient/releases/download/v$version/$archive"
tmp="$(mktemp -d -t twinconnect-trusttunnel)"
trap 'rm -rf -- "$tmp"' EXIT
/usr/bin/curl --fail --location --silent --show-error --retry 2 --max-time 110 \
  --output "$tmp/$archive" "$url"
echo "$sha  $tmp/$archive" | /usr/bin/shasum -a 256 -c - >/dev/null || {
  echo "TRUSTTUNNEL_HASH_MISMATCH" >&2; exit 3;
}
/usr/bin/tar xzf "$tmp/$archive" -C "$tmp"
src="$tmp/trusttunnel_client-v$version-macos-universal/trusttunnel_client"
[[ -f "$src" && ! -L "$src" && -x "$src" ]] || {
  echo "TRUSTTUNNEL_RELEASE_INVALID" >&2; exit 3;
}
/usr/bin/lipo -archs "$src" | tr ' ' '\n' | grep -Fxq x86_64 || {
  echo "TRUSTTUNNEL_ARCH_UNSUPPORTED" >&2; exit 3;
}
"$src" --version 2>&1 | grep -Fqx "trusttunnel_client $version" || {
  echo "TRUSTTUNNEL_RELEASE_VERSION_MISMATCH" >&2; exit 3;
}
dest="macos_native/build/trusttunnel/amd64"
mkdir -p "$dest"
[[ ! -L "$dest" ]] || {
  echo "TRUSTTUNNEL_DESTINATION_SYMLINK_REJECTED" >&2; exit 3;
}
/usr/bin/install -m 0755 "$src" "$dest/trusttunnel_client"
echo "TRUSTTUNNEL_OFFICIAL_CLIENT_HASH_VERIFIED_LOCAL_ONLY"