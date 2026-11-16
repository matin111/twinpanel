#!/usr/bin/env python3
"""Inspect actual APK contents without extracting private signed artifacts."""
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

apk = Path(sys.argv[1])
if not apk.is_file():
    raise SystemExit(f"Missing release APK: {apk}")
with zipfile.ZipFile(apk) as archive:
    files = [entry for entry in archive.infolist() if not entry.is_dir()]
    sizes = defaultdict(int)
    libraries = []
    for entry in files:
        group = entry.filename.split('/', 1)[0]
        sizes[group] += entry.compress_size
        if entry.filename.endswith('.so'):
            libraries.append((entry.file_size, entry.compress_size, entry.filename))
    print(f"APK: {apk.stat().st_size / 1048576:.2f} MiB ({apk.stat().st_size} bytes)")
    print("Compressed top-level components:")
    for group, size in sorted(sizes.items(), key=lambda x: -x[1]):
        print(f"  {size / 1048576:8.2f} MiB  {group}")
    print("Largest native libraries (uncompressed / stored inside APK):")
    for raw, packed, path in sorted(libraries, reverse=True)[:30]:
        print(f"  {raw / 1048576:8.2f} / {packed / 1048576:8.2f} MiB  {path}")
    print(f"Total .so libraries: {len(libraries)}")
