#!/usr/bin/env python3
"""Bundle a Homebrew OpenVPN CLI and non-system dylibs in an unsigned macOS app.

Offline packaging ONLY. Never execute OpenVPN, escalate privileges, or edit
routes. Rewrite absolute Homebrew loads to relocatable @loader_path references.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

BREW_PREFIXES = ("/usr/local/", "/opt/homebrew/")
SYSTEM_PREFIXES = ("/usr/lib/", "/System/Library/")
MAX_LIBRARIES = 96


def dependencies(path: Path) -> list[str]:
    data = subprocess.run(["/usr/bin/otool", "-L", str(path)], check=True,
                          capture_output=True, text=True, timeout=15).stdout
    return [line.strip().split(" (", 1)[0] for line in data.splitlines()[1:]
            if " (" in line]


def inspect_arch(path: Path, arch: str) -> None:
    data = subprocess.run(["/usr/bin/lipo", "-archs", str(path)], check=True,
                          capture_output=True, text=True, timeout=15).stdout.split()
    if arch not in data:
        raise ValueError("OPENVPN_ARCH_MISMATCH")


def package(binary: Path, output: Path, arch: str) -> int:
    if not binary.is_file() or binary.is_symlink():
        raise ValueError("OPENVPN_BINARY_MISSING")
    inspect_arch(binary, arch)
    if output.exists() or output.is_symlink():
        raise ValueError("OPENVPN_DESTINATION_EXISTS")
    executable = output / "bin/openvpn"
    libdir = output / "lib"
    libdir.mkdir(parents=True)
    executable.parent.mkdir(parents=True)
    shutil.copy2(binary, executable)
    os.chmod(executable, 0o755)
    found: dict[str, Path] = {}
    names: dict[str, str] = {}
    waiting = [executable]

    while waiting:
        obj = waiting.pop()
        for dep in dependencies(obj):
            # otool -L includes each dylib's *own install name* as its
            # first entry. It is metadata, not another library to copy.
            # Rewriting it with install_name_tool -id happens below.
            if obj != executable and dep.startswith(BREW_PREFIXES) and Path(dep).name == obj.name:
                continue
            if dep.startswith(SYSTEM_PREFIXES) or dep.startswith("@"):
                continue
            if not dep.startswith(BREW_PREFIXES):
                raise ValueError("UNEXPECTED_ABSOLUTE_DYLIB")
            original = Path(dep)
            if not original.is_file():
                raise ValueError("OPENVPN_DYLIB_NOT_FOUND")
            if dep not in found:
                if len(found) >= MAX_LIBRARIES:
                    raise ValueError("EXCESSIVE_OPENVPN_DYLIBS")
                name = original.name
                if name in names and names[name] != dep:
                    raise ValueError("AMBIGUOUS_DYLIB_BASENAME")
                names[name] = dep
                target = libdir / name
                if target.exists():
                    raise ValueError("DYLIB_COLLISION")
                inspect_arch(original, arch)
                shutil.copy2(original, target)
                os.chmod(target, 0o755)
                found[dep] = target
                waiting.append(target)
            reference = ("@loader_path/../lib/" if obj == executable
                         else "@loader_path/") + original.name
            subprocess.run(["/usr/bin/install_name_tool", "-change", dep,
                            reference, str(obj)], check=True, timeout=15)
        if obj != executable:
            subprocess.run(["/usr/bin/install_name_tool", "-id",
                            "@loader_path/" + obj.name, str(obj)],
                           check=True, timeout=15)

    for item in [executable, *found.values()]:
        for dep in dependencies(item):
            if dep.startswith(BREW_PREFIXES):
                raise ValueError("UNRELOCATED_HOMEBREW_DYLIB")
            if not (dep.startswith(SYSTEM_PREFIXES) or dep.startswith("@loader_path/")):
                raise ValueError("UNEXPECTED_RUNTIME_DYLIB")
    return len(found)


def main() -> int:
    if len(sys.argv) != 4:
        print("USAGE: package_openvpn_cli.py /path/to/openvpn /output/dir x86_64|arm64",
              file=sys.stderr)
        return 2
    source, output, arch = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    if sys.platform != "darwin" or arch not in ("x86_64", "arm64"):
        print("MACOS_ARCH_REQUIRED", file=sys.stderr)
        return 2
    try:
        count = package(source, output, arch)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print("OPENVPN_BUNDLE_FAILED: " + str(error), file=sys.stderr)
        return 3
    print("OPENVPN_CLI_PACKAGED: " + str(count) + " libraries")
    print("OPENVPN_CLI_NOT_CONNECTED; NO_SYSTEM_ROUTE_CHANGED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
