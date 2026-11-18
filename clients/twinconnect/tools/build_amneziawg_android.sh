#!/usr/bin/env bash
# Build the official AmneziaWG Android native tunnel AAR from source.
# Stages a JNI-isolated AAR for the Android installer.
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
# Discard previous local loader/SONAME patches on repeated builds.
git -C "$SOURCE_DIR" restore -- tunnel/src/main/java/org/amnezia/awg/backend/GoBackend.java tunnel/tools/libwg-go/Makefile
# The upstream Gradle project requires a package name supplied externally.
export ORG_GRADLE_PROJECT_amneziawgPackageName=org.amnezia.awg
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
# The native ELF SONAME must also differ; merely renaming the ZIP entry
# does not isolate two Go shared libraries in the Android linker.
python3 - "$SOURCE_DIR" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1]) / "tunnel/tools/libwg-go/Makefile"
s = p.read_text()
old = "-Wl,-soname=libwg-go.so"
new = "-Wl,-soname=libawg-go.so"
if old in s:
    p.write_text(s.replace(old, new))
elif new not in s:
    raise SystemExit("Unexpected AWG native linker SONAME")
PY
(
  cd "$SOURCE_DIR"
  ANDROID_PACKAGE_NAME=com.twinpanel.twinconnect ./gradlew --no-daemon :tunnel:assembleRelease
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
import sys, zipfile, re
src, dst = sys.argv[1:]
with zipfile.ZipFile(src) as source, zipfile.ZipFile(dst, "w") as target:
    for item in source.infolist():
        data = source.read(item.filename)
        name = item.filename
        if name == "AndroidManifest.xml":
            # The AAR's manifest would merge in a second independent Android
            # VPN service, even if the host manifest never mentions it.
            # TwinConnect loads AWG's pinned JNI directly via SharedTunVpnService.
            xml = data.decode("utf-8")
            pattern = (r'\s*<service\b[^>]*android:name="'
                       r'org\.amnezia\.awg\.backend\.GoBackend\$VpnService"'
                       r'[^>]*>.*?</service>')
            xml, removed = re.subn(pattern, "", xml, flags=re.DOTALL)
            if removed != 1:
                raise SystemExit("Expected one upstream AWG VpnService manifest entry")
            data = xml.encode("utf-8")
        # GoBackend uses libawg-go.so. The upstream AAR also contains
        # libwg-quick.so for the unused WgQuickBackend; stock WireGuard
        # already supplies that exact JNI name. Never bundle two copies.
        if name.startswith("jni/") and (
            name.endswith("/libwg-quick.so") or name.endswith("/libwg.so")
        ):
            # Both belong to the upstream optional WgQuickBackend and
            # collide with the stock WireGuard tunnel dependency.
            continue
        if name.startswith("jni/") and name.endswith("/libwg-go.so"):
            name = name[:-len("libwg-go.so")] + "libawg-go.so"
        target.writestr(name, data)
with zipfile.ZipFile(dst) as staged:
    names = staged.namelist()
    assert any(n.endswith("/libawg-go.so") for n in names)
    assert not any(n.endswith("/libwg-go.so") for n in names)
    assert not any(n.endswith("/libwg-quick.so") for n in names)
    assert not any(n.endswith("/libwg.so") for n in names)
    assert b'org.amnezia.awg.backend.GoBackend$VpnService' not in staged.read(
        'AndroidManifest.xml'), 'Staged AWG AAR still registers a second VPN'
print("AWG native loader isolated from stock WireGuard JNI name")
PY
echo "Staged collision-free AWG AAR: $OUT/tunnel-release.aar"
echo "AWG AAR staged. The installer integrates it when present; device verification is still required."

