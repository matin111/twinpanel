#!/usr/bin/env bash
set -Eeuo pipefail

OUTPUT_PATH="${1:?usage: build-netmod-udpgw.sh OUTPUT_PATH [LICENSE_PATH]}"
LICENSE_PATH="${2:-$(dirname "$OUTPUT_PATH")/badvpn-COPYING}"
BADVPN_COMMIT='07268f02706e78e282e19641b5d1d41e8e89bf31'
TEST_PORT="${NETMOD_UDPGW_TEST_PORT:-17300}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PATCHER="$SCRIPT_DIR/patch-badvpn-udpgw-resolver.py"

for cmd in git cmake gcc file ss sha256sum python3; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "NETMOD_UDPGW_BUILD_MISSING_TOOL=$cmd" >&2
    exit 31
  }
done

test -s "$PATCHER" || {
  echo "NETMOD_UDPGW_PATCHER_MISSING=$PATCHER" >&2
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

# Transform only exact snippets from the immutable upstream source. The patcher
# requires exactly one match for each target and fails closed if upstream ever
# differs, avoiding fragile line-number based unified patches.
python3 "$PATCHER" "$SRC/udpgw/udpgw.c"
git -C "$SRC" diff --check
grep -Fq 'loaded DNS server from /etc/resolv.conf fallback' "$SRC/udpgw/udpgw.c"
grep -Fq 'res_init() == 0 && _res.nscount > 0' "$SRC/udpgw/udpgw.c"

# Keep the rc.233 self-contained glibc-static artifact model, but patch the
# exact production failure: upstream BadVPN only trusts res_init/_res. The
# deterministic transformer preserves that path first and reads the first valid
# IPv4 nameserver from /etc/resolv.conf only when libc exposes no resolver.
CC=gcc cmake -S "$SRC" -B "$BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_NOTHING_BY_DEFAULT=1 \
  -DBUILD_UDPGW=1 \
  -DCMAKE_EXE_LINKER_FLAGS='-static'
cmake --build "$BUILD" --target badvpn-udpgw --parallel 2

BIN="$BUILD/udpgw/badvpn-udpgw"
test -x "$BIN"
"$BIN" --version | grep -q 'BadVPN udpgw'
file "$BIN" | grep -q 'statically linked'

# Validate resolver initialization, not merely the TCP listener. Production
# rc.233 proved a glibc-static binary can listen while _res.nscount is empty.
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

install -D -m 0755 "$BIN" "$OUTPUT_PATH"
install -D -m 0644 "$SRC/COPYING" "$LICENSE_PATH"
sha256sum "$OUTPUT_PATH" > "${OUTPUT_PATH}.sha256"

printf 'NETMOD_UDPGW_BUILD_OK=%s\n' "$OUTPUT_PATH"
printf 'NETMOD_UDPGW_LICENSE=%s\n' "$LICENSE_PATH"
printf 'NETMOD_UDPGW_RESOLVER=verified\n'
cat "$LOG"
