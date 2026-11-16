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
# The official AWG backend loads "wg-go", which collides with the stock
# WireGuard backend bundled by TwinConnect. Patch ONLY the AWG source tree
# and package its JNI library under a distinct loader name.
python3 - "$SOURCE_DIR" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
java = root / "tunnel/src/main/java/org/amnezia/awg/backend/GoBackend.java"
source = java.read_text()
original = 'SharedLibraryLoader.loadSharedLibrary(context, "wg-go")'
renamed = 'SharedLibraryLoader.loadSharedLibrary(context, "awg-go")'
if original in source:
    java.write_text(source.replace(original, renamed))
elif renamed not in source:
    raise SystemExit("Unexpected upstream GoBackend library loader")
PY
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
# Keep the upstream build output intact; rewrite only the staged AAR's JNI
# filenames. The patched GoBackend loader resolves libawg-go.so while the
# existing WireGuard backend continues to resolve its own libwg-go.so.
python3 - "$AAR" "$OUT/tunnel-release.aar" <<'PY'
import sys, zipfile
src, dst = sys.argv[1:]
with zipfile.ZipFile(src) as source, zipfile.ZipFile(dst, "w") as target:
    for item in source.infolist():
        data = source.read(item.filename)
        name = item.filename
        if name.startswith("jni/") and name.endswith("/libwg-go.so"):
            name = name[:-len("libwg-go.so")] + "libawg-go.so"
        target.writestr(name, data)
with zipfile.ZipFile(dst) as staged:
    names = staged.namelist()
    assert any(n.endswith("/libawg-go.so") for n in names)
    assert not any(n.endswith("/libwg-go.so") for n in names)
print("AWG native loader isolated from stock WireGuard JNI name")
PY
echo "Staged collision-free AWG AAR: $OUT/tunnel-release.aar"
echo "NOT integrated into APK: VpnService wiring and device tests still required."
