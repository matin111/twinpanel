#!/usr/bin/env bash
# Build the official AmneziaWG Android native tunnel AAR from source.
# This does not install the AAR into the TwinConnect APK: the existing
# WireGuard dependency exports the same libwg-go.so JNI filename.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/native/android/amneziawg-core"
SOURCE_DIR="${AWG_SOURCE_DIR:-$OUT/upstream}"
REVISION="${AWG_REVISION:?Set AWG_REVISION to a reviewed upstream commit SHA}"
if [[ ! "$REVISION" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "AWG_REVISION must be a full 40-character commit SHA" >&2
  exit 2
fi
mkdir -p "$OUT"
if [[ ! -d "$SOURCE_DIR/.git" ]]; then
  git clone --recurse-submodules https://github.com/amnezia-vpn/amneziawg-android.git "$SOURCE_DIR"
fi
git -C "$SOURCE_DIR" fetch origin "$REVISION"
git -C "$SOURCE_DIR" checkout --detach "$REVISION"
git -C "$SOURCE_DIR" submodule update --init --recursive
(
  cd "$SOURCE_DIR"
  ./gradlew --no-daemon :tunnel:assembleRelease
)
AAR="$SOURCE_DIR/tunnel/build/outputs/aar/tunnel-release.aar"
test -s "$AAR"
python3 - "$AAR" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    names = set(z.namelist())
    assert 'classes.jar' in names, 'Missing Java backend'
    for abi in ('arm64-v8a', 'armeabi-v7a', 'x86_64'):
        assert f'jni/{abi}/libwg-go.so' in names, f'Missing {abi} native engine'
print('Verified official AmneziaWG native AAR')
PY
cp "$AAR" "$OUT/tunnel-release.aar"
echo "Staged: $OUT/tunnel-release.aar"
echo "NOT integrated into APK: independent JNI loading and VpnService still required."
