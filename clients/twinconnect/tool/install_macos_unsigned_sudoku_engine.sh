#!/usr/bin/env bash
# Official, hash-pinned core. No route or DNS changes.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin ]] || exit 2
case "$(uname -m)" in
 x86_64) arch=amd64; hash=256130dee6d9864a604ebe05a7cc23c86d92a3cfcfa346dbf23ce9a9a323704d;;
 arm64) arch=arm64; hash=89717753dd339a05e8bd62cbd7d154ad6985b9340e5e9317f45719f5c826fd51;;
 *) exit 2;;
esac
tmp="$(mktemp -d -t twinconnect-sudoku)"
trap 'rm -rf -- "$tmp"' EXIT
curl -fLsS --max-time 90 "https://github.com/SUDOKU-ASCII/sudoku/releases/download/v0.5.2-1/sudoku-darwin-$arch.tar.gz" -o "$tmp/core.tar.gz"
[[ "$(shasum -a 256 "$tmp/core.tar.gz" | awk '{print $1}')" == "$hash" ]] || { echo SUDOKU_HASH_MISMATCH; exit 3; }
python3 - "$tmp" <<'EXTRACT'
import pathlib,sys,tarfile,shutil
p=pathlib.Path(sys.argv[1])
with tarfile.open(p/'core.tar.gz') as t:
    matches=[m for m in t.getmembers() if pathlib.PurePosixPath(m.name).name=='sudoku' and m.isfile()]
    assert len(matches)==1 and 1000000<matches[0].size<100000000
    with t.extractfile(matches[0]) as source,(p/'sudoku').open('xb') as dest:
        shutil.copyfileobj(source,dest)
(p/'sudoku').chmod(0o755)
EXTRACT
"$tmp/sudoku" -h >/dev/null 2>&1
out="macos_native/build/sudoku/$arch"
[[ ! -L "$out" && ! -L "$out/sudoku" ]]
mkdir -p "$out"
install -m 0755 "$tmp/sudoku" "$out/sudoku"
echo SUDOKU_OFFICIAL_CORE_STAGED_NO_NETWORK_CHANGES
