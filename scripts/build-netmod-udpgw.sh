#!/usr/bin/env bash
set -Eeuo pipefail

OUTPUT_PATH="${1:?usage: build-netmod-udpgw.sh OUTPUT_PATH [LICENSE_PATH]}"
LICENSE_PATH="${2:-$(dirname "$OUTPUT_PATH")/badvpn-COPYING}"
BADVPN_COMMIT='07268f02706e78e282e19641b5d1d41e8e89bf31'
TEST_PORT="${NETMOD_UDPGW_TEST_PORT:-17300}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PATCH_PATH="$SCRIPT_DIR/patches/badvpn-udpgw-resolvconf-fallback.patch"

for cmd in git cmake musl-gcc file ss sha256sum; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "NETMOD_UDPGW_BUILD_MISSING_TOOL=$cmd" >&2
    exit 31
  }
done

test -s "$PATCH_PATH" || {
  echo "NETMOD_UDPGW_PATCH_MISSING=$PATCH_PATH" >&2
  exit 30
}

SRC="$(mktemp -d)"
BUILD="$(mktemp -d)"
LOG="$(mktemp)"
PID=""
cleanup() {
  if [ -n "$PID" ]; then
    kill "$PID" >/dev/null 2>&1 || true
    wait "$PID" >/dev/null 2>&1 || true
  fi
  rm -rf "$SRC" "$BUILD"
  rm -f "$LOG"
}
trap cleanup EXIT

git -C "$SRC" init -q
git -C "$SRC" remote add origin https://github.com/ambrop72/badvpn.git
git -C "$SRC" fetch -q --depth=1 origin "$BADVPN_COMMIT"
git -C "$SRC" checkout -q --detach FETCH_HEAD
test "$(git -C "$SRC" rev-parse HEAD)" = "$BADVPN_COMMIT"

git -C "$SRC" apply --check "$PATCH_PATH"
git -C "$SRC" apply "$PATCH_PATH"
git -C "$SRC" diff --check
grep -Fq 'loaded DNS server from /etc/resolv.conf fallback' "$SRC/udpgw/udpgw.c"

# Keep the artifact self-contained. The upstream resolver path depends on
# res_init/_res and production proved that both musl-static and glibc-static
# builds may expose an empty resolver state even with a valid resolv.conf.
# The pinned patch preserves the upstream path first and only falls back to
# parsing the first IPv4 nameserver from /etc/resolv.conf when _res is empty.
CC=musl-gcc cmake -S "$SRC" -B "$BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_NOTHING_BY_DEFAULT=1 \
  -DBUILD_UDPGW=1 \
  -DCMAKE_EXE_LINKER_FLAGS='-static'
cmake --build "$BUILD" --target badvpn-udpgw --parallel 2

BIN="$BUILD/udpgw/badvpn-udpgw"
test -x "$BIN"
"$BIN" --version | grep -q 'BadVPN udpgw'
file "$BIN" | grep -q 'statically linked'

# The gate validates resolver initialization, not merely the TCP listener.
# On musl-static the upstream _res path is the exact failure mode observed in
# production, so this probe also exercises the resolv.conf fallback itself.
"$BIN" \
  --logger stdout \
  --loglevel info \
  --listen-addr "127.0.0.1:${TEST_PORT}" \
  --max-clients 8 \
  --max-connections-for-client 32 \
  >"$LOG" 2>&1 &
PID=$!

for _ in $(seq 1 50); do
  if ss -H -ltn | grep -F "127.0.0.1:${TEST_PORT} " >/dev/null; then
    break
  fi
  if ! kill -0 "$PID" >/dev/null 2>&1; then
    cat "$LOG" >&2
    echo "NETMOD_UDPGW_PROBE_EXITED_EARLY" >&2
    exit 32
  fi
  sleep 0.1
done

if ! ss -H -ltn | grep -F "127.0.0.1:${TEST_PORT} " >/dev/null; then
  cat "$LOG" >&2
  echo "NETMOD_UDPGW_PROBE_LISTENER_MISSING" >&2
  exit 33
fi

# Flush stdout before inspecting resolver messages.
sleep 0.2
kill "$PID" >/dev/null 2>&1 || true
wait "$PID" >/dev/null 2>&1 || true
PID=""

if grep -Fq 'no name servers available' "$LOG"; then
  cat "$LOG" >&2
  echo "NETMOD_UDPGW_RESOLVER_UNAVAILABLE" >&2
  exit 34
fi
if ! grep -Fq 'using DNS server' "$LOG"; then
  cat "$LOG" >&2
  echo "NETMOD_UDPGW_RESOLVER_NOT_CONFIRMED" >&2
  exit 35
fi
if ! grep -Fq 'loaded DNS server from /etc/resolv.conf fallback' "$LOG"; then
  cat "$LOG" >&2
  echo "NETMOD_UDPGW_RESOLVCONF_FALLBACK_NOT_EXERCISED" >&2
  exit 36
fi

install -D -m 0755 "$BIN" "$OUTPUT_PATH"
install -D -m 0644 "$SRC/COPYING" "$LICENSE_PATH"
sha256sum "$OUTPUT_PATH" > "${OUTPUT_PATH}.sha256"

printf 'NETMOD_UDPGW_BUILD_OK=%s\n' "$OUTPUT_PATH"
printf 'NETMOD_UDPGW_LICENSE=%s\n' "$LICENSE_PATH"
printf 'NETMOD_UDPGW_RESOLVER=fallback-verified\n'
cat "$LOG"
