#!/usr/bin/env bash
# Reproducible, hash-pinned unsigned Mieru outbound engine for macOS x86_64.
# Does not install root services, start a VPN, or alter networking.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin && "$(uname -m)" == x86_64 ]] || {
  echo "DARWIN_AMD64_REQUIRED" >&2; exit 2;
}
version="1.14.3"
sha="f66f8961c1a4a5d1b32dbec93e4c3fd41280410c9011aeca79b0faa690ab893f"
archive="sing-box-$version-darwin-amd64.tar.gz"
url="https://github.com/enfein/mbox/releases/download/v$version/$archive"
stage="$(mktemp -d -t twinconnect-mbox)"
trap 'rm -rf -- "$stage"' EXIT
/usr/bin/curl -fL --retry 2 --max-time 100 -o "$stage/$archive" "$url"
echo "$sha  $stage/$archive" | /usr/bin/shasum -a 256 -c - >/dev/null || {
  echo "MIERU_MBOX_HASH_MISMATCH" >&2; exit 3;
}
tar -xzf "$stage/$archive" -C "$stage"
source="$stage/sing-box-$version-darwin-amd64/sing-box"
[[ -f "$source" && ! -L "$source" && -x "$source" ]] || {
  echo "MIERU_MBOX_RELEASE_INVALID" >&2; exit 3;
}
/usr/bin/lipo -archs "$source" | grep -qw x86_64 || {
  echo "MIERU_MBOX_WRONG_ARCH" >&2; exit 3;
}
[[ "$("$source" version | head -1)" == "sing-box version $version" ]] || {
  echo "MIERU_MBOX_VERSION_INVALID" >&2; exit 3;
}
destination="macos_native/build/mbox/amd64"
mkdir -p "$destination"
[[ ! -L "$destination" ]] || {
  echo "MIERU_MBOX_INSTALL_SYMLINK_REFUSED" >&2; exit 3;
}
install -m 0755 "$source" "$destination/sing-box"
echo "MIERU_MBOX_UNSIGNED_ENGINE_VERIFIED_AND_STAGED"