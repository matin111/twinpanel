#!/usr/bin/env bash
# Build the real upstream Mieru client for Android ABIs.
# This produces a native executable, NOT a complete VpnService/TUN bridge.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIERU_REV="4000e447c994d3382e96e524139a369fca92829b"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
: "${ANDROID_NDK_HOME:?Set ANDROID_NDK_HOME to a supported Android NDK}"
: "${GO:?Set GO to the Go executable, e.g. GO=go}"
HOST_TAG="${ANDROID_NDK_HOST_TAG:-linux-x86_64}"
TOOLCHAIN="$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/$HOST_TAG/bin"
test -d "$TOOLCHAIN" || { echo "NDK toolchain missing" >&2; exit 1; }

git clone --filter=blob:none https://github.com/enfein/mieru.git "$WORK/mieru"
git -C "$WORK/mieru" checkout --detach "$MIERU_REV"
mkdir -p "$ROOT/native/android/mieru-jni"
for ABI in arm64-v8a armeabi-v7a x86_64; do
  case "$ABI" in
    arm64-v8a) GOARCH=arm64; CLANG=aarch64-linux-android24-clang;;
    armeabi-v7a) GOARCH=arm; CLANG=armv7a-linux-androideabi24-clang;;
    x86_64) GOARCH=amd64; CLANG=x86_64-linux-android24-clang;;
  esac
  OUT="$ROOT/native/android/mieru-jni/$ABI"
  mkdir -p "$OUT"
  (cd "$WORK/mieru" && GOOS=android GOARCH="$GOARCH" CGO_ENABLED=1 \
    CC="$TOOLCHAIN/$CLANG" "$GO" build -trimpath \
    -ldflags="-s -w" -o "$OUT/libmieru.so" ./cmd/mieru)
  file "$OUT/libmieru.so"
done
echo "Mieru Android binaries built; Android VpnService integration still required."
