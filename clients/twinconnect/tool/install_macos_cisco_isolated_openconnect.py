#!/usr/bin/env python3
"""Build a private, root-owned OpenConnect runtime for TwinConnect on macOS.

Administrator-invoked, offline. Copies the Homebrew executable and its full
Mach-O dependency closure, rewrites load commands into a private library dir,
ad-hoc signs copied binaries, and verifies no Homebrew paths remain.
No VPN is started and no network settings or sudoers are changed.
"""
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

BASE = Path("/Library/PrivilegedHelperTools/TwinConnectCisco")
DEST = BASE / "openconnect-runtime"
SYSTEM = ("/usr/lib/", "/System/Library/")
MAX_FILES = 128


def command(*args):
    p = subprocess.run(args, text=True, capture_output=True, check=False, timeout=30)
    if p.returncode:
        raise RuntimeError("CISCO_BUNDLE_COMMAND_FAILED")
    return p.stdout


def dependency_info(path):
    lines = command("/usr/bin/otool", "-L", str(path)).splitlines()[1:]
    return [line.strip().split(" (", 1)[0] for line in lines if " (" in line]


def install_id(path):
    # Mach-O executables generally have no LC_ID_DYLIB load command.
    result = subprocess.run(
        ["/usr/bin/otool", "-D", str(path)], capture_output=True,
        text=True, check=False, timeout=30)
    lines = result.stdout.splitlines()
    return lines[1].strip() if result.returncode == 0 and len(lines) > 1 else None


def closure(source):
    pending = [str(source)]
    found = {}
    while pending:
        item = pending.pop()
        real = str(Path(item).resolve(strict=True))
        if real in found:
            continue
        if len(found) >= MAX_FILES:
            raise RuntimeError("CISCO_BUNDLE_TOO_MANY_DEPENDENCIES")
        if not Path(real).is_file():
            raise RuntimeError("CISCO_BUNDLE_INVALID_FILE")
        ident = install_id(real)
        deps = dependency_info(real)
        found[real] = (ident, deps)
        for dep in deps:
            if dep == ident:
                continue
            if dep.startswith(SYSTEM):
                continue
            if not dep.startswith("/"):
                raise RuntimeError("CISCO_BUNDLE_UNRESOLVED_LOAD_PATH")
            if not dep.startswith(("/usr/local/", "/opt/homebrew/")):
                raise RuntimeError("CISCO_BUNDLE_EXTERNAL_DEPENDENCY")
            pending.append(dep)
    return found


def verify_paths(targets):
    for path in targets:
        ident = install_id(path)
        for dep in dependency_info(path):
            if dep == ident or dep.startswith(SYSTEM):
                continue
            if not dep.startswith("@loader_path/"):
                raise RuntimeError("CISCO_BUNDLE_VERIFY_FAILED")
            resolved = (path.parent / dep[len("@loader_path/"):]).resolve()
            if not resolved.is_file() or not resolved.is_relative_to(path.parents[1]):
                raise RuntimeError("CISCO_BUNDLE_VERIFY_FAILED")


def build():
    if sys.platform != "darwin" or os.geteuid() != 0:
        raise RuntimeError("CISCO_MACOS_ROOT_REQUIRED")
    if len(sys.argv) != 2 or sys.argv[1] != "--install":
        raise RuntimeError("CISCO_BUNDLE_ACTION_INVALID")
    st = BASE.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
        raise RuntimeError("CISCO_HELPER_DIRECTORY_UNSAFE")
    source = next((x for x in (
        "/usr/local/bin/openconnect", "/opt/homebrew/bin/openconnect"
    ) if Path(x).is_file()), None)
    if source is None:
        raise RuntimeError("CISCO_OPENCONNECT_NOT_FOUND")
    files = closure(source)
    resolved_exe = str(Path(source).resolve(strict=True))
    # Unique names avoid collisions between libraries from different formulas.
    names = {p: (Path(p).stem + "-" + hashlib.sha256(p.encode()).hexdigest()[:12]
                  + Path(p).suffix) for p in files if p != resolved_exe}
    staging = Path(tempfile.mkdtemp(prefix=".openconnect-stage-", dir=BASE))
    try:
        # mkdtemp defaults to 0700. The final root-owned runtime must be
        # traversable by the signed-in user for version/signature diagnostics.
        # Ownership of all binaries and libraries remains root:wheel.
        os.chmod(staging, 0o755)
        bindir = staging / "bin"
        libdir = staging / "lib"
        bindir.mkdir(mode=0o755)
        libdir.mkdir(mode=0o755)
        targets = {p: (bindir / "openconnect" if p == resolved_exe
                       else libdir / names[p]) for p in files}
        for source_path, destination in targets.items():
            shutil.copyfile(source_path, destination)
            os.chmod(destination, 0o755 if source_path == resolved_exe else 0o644)
        for src, (ident, dependencies) in files.items():
            target = targets[src]
            for dep in dependencies:
                if dep == ident or dep.startswith(SYSTEM):
                    continue
                real = str(Path(dep).resolve(strict=True))
                relative = os.path.relpath(targets[real], target.parent)
                command("/usr/bin/install_name_tool", "-change", dep,
                        "@loader_path/" + relative, str(target))
            if src != resolved_exe and ident:
                command("/usr/bin/install_name_tool", "-id",
                        "@loader_path/" + targets[src].name, str(target))
        # Check copied paths after rewrite before granting executable permissions.
        verify_paths(targets.values())
        for target in targets.values():
            command("/usr/bin/codesign", "--force", "--sign", "-", str(target))
        verify_paths(targets.values())
        for target in targets.values():
            command("/usr/bin/codesign", "--verify", "--strict", str(target))
        os.chown(bindir, 0, 0)
        os.chown(libdir, 0, 0)
        for target in targets.values():
            os.chown(target, 0, 0)
        # No in-place edits of a live runtime; replace after successful build.
        backup = BASE / ".openconnect-runtime-previous"
        if backup.exists():
            shutil.rmtree(backup)
        if DEST.exists():
            DEST.rename(backup)
        staging.rename(DEST)
        if backup.exists():
            shutil.rmtree(backup)
        print("CISCO_ISOLATED_OPENCONNECT_INSTALLED")
        print("FILES:", len(targets))
        print("VPN_NOT_STARTED; SUDOERS_UNCHANGED")
    finally:
        if staging.exists():
            shutil.rmtree(staging)


if __name__ == "__main__":
    try:
        build()
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        msg = str(exc)
        if not re.fullmatch(r"CISCO_[A-Z0-9_]+", msg):
            msg = "CISCO_BUNDLE_FAILED"
        print(msg, file=sys.stderr)
        raise SystemExit(1)
