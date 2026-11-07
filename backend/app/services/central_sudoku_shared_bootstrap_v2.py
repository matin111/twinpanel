"""Install a pinned, multiuser-capable Sudoku daemon ONCE per Exit.

The legacy sudoku binary and all legacy services are untouched. The controller
builds a pinned upstream checkout once (or consumes a prebuilt hash-verified
artifact), then transfers that binary to the hidden node over its saved SSH
management connection. No public download, git, Go, SSH or service restart per
subscription.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

from ..node_runtime_connection import connect_protocol_runtime

UPSTREAM = "https://github.com/SUDOKU-ASCII/sudoku.git"
UPSTREAM_COMMIT = "b1d1f0e767653d2c70e2ff814a01264c7dedf1f4"
BINARY_SHA256 = "9c0ab370a30d89f076b0639fcdef01d9e191d44ee18178b36b83cfa7192d8e3d"
TARGET = "/usr/local/bin/twinpanel-sudoku-shared"
CACHE_DIR = Path("/opt/twinpanel/central-binaries")


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def _check_binary(path: Path) -> Path:
    if not path.is_file() or path.is_symlink() or _digest(path) != BINARY_SHA256:
        raise RuntimeError("SUDOKU_SHARED_PINNED_BINARY_MISMATCH")
    return path


def build_pinned_binary() -> Path:
    """Controller only; build once in a temporary checkout, never on new Exit."""
    override = os.environ.get("TWINPANEL_SUDOKU_SHARED_BINARY")
    if override:
        return _check_binary(Path(override))
    CACHE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    output = CACHE_DIR / ("sudoku-shared-" + BINARY_SHA256)
    if output.is_file():
        return _check_binary(output)
    if not shutil.which("git") or not shutil.which("go"):
        raise RuntimeError("SUDOKU_SHARED_BUILD_TOOLCHAIN_UNAVAILABLE")
    # Lock protects first-use builds when two Exit nodes are added at once.
    import fcntl
    with (CACHE_DIR / "sudoku-shared-build.lock").open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        if output.is_file():
            return _check_binary(output)
        with tempfile.TemporaryDirectory(prefix="tp-sudoku-build-", dir=CACHE_DIR) as work:
            root = Path(work)
            source = root / "upstream"
            subprocess.run(
                ["git", "clone", "--quiet", "--no-checkout", UPSTREAM, str(source)],
                check=True, timeout=180, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                ["git", "-C", str(source), "checkout", "--quiet", UPSTREAM_COMMIT],
                check=True, timeout=60,
            )
            built = root / "sudoku-shared"
            subprocess.run(
                ["go", "build", "-trimpath", "-o", str(built), "./cmd/sudoku-tunnel"],
                cwd=source, check=True, timeout=720, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**os.environ, "GOTOOLCHAIN":"auto", "GOMAXPROCS":"4"},
            )
            _check_binary(built)
            os.chmod(built, 0o755)
            os.replace(built, output)
    return _check_binary(output)


async def ensure_shared_binary(node, db) -> dict:
    """Node SSH invoked once; fail closed on unpinned target installations."""
    conn = await asyncio.wait_for(connect_protocol_runtime(node, db), timeout=25)
    try:
        probe = await asyncio.wait_for(conn.run(
            "if test -f " + shlex.quote(TARGET) + "; then sha256sum " +
            shlex.quote(TARGET) + " | cut -d' ' -f1; else printf 'missing'; fi",
            check=False,
        ), timeout=15)
        if probe.exit_status:
            raise RuntimeError("SUDOKU_SHARED_TARGET_PROBE_FAILED")
        found = probe.stdout.strip()
        if found == BINARY_SHA256:
            return {"ok": True, "binary_ready": True, "installed_now": False}
        if found != "missing":
            raise RuntimeError("SUDOKU_SHARED_TARGET_BINARY_UNRECOGNIZED")
        source = await asyncio.to_thread(build_pinned_binary)
        # Put the file in the destination filesystem before atomic install.
        # The binary contains no credentials. Existing sudo binary untouched.
        temp = TARGET + ".stage-" + str(os.getpid())
        try:
            async with conn.start_sftp_client() as sftp:
                await asyncio.wait_for(
                    sftp.put(str(source),temp),timeout=120,
                )
            command = (
                "set -eu; "
                + "test \"$(sha256sum " + shlex.quote(temp)
                + " | cut -d' ' -f1)\" = " + shlex.quote(BINARY_SHA256)
                + "; install -m 0755 " + shlex.quote(temp)
                + " " + shlex.quote(TARGET)
                + "; rm -f " + shlex.quote(temp)
                + "; sha256sum " + shlex.quote(TARGET) + " | cut -d' ' -f1"
            )
            result=await asyncio.wait_for(conn.run(command,check=False),timeout=50)
            if result.exit_status or result.stdout.strip()!=BINARY_SHA256:
                raise RuntimeError("SUDOKU_SHARED_TARGET_INSTALL_FAILED")
        finally:
            await conn.run("rm -f " + shlex.quote(temp), check=False)
        return {"ok":True, "binary_ready": True, "installed_now": True}
    finally:
        conn.close()
        await conn.wait_closed()
