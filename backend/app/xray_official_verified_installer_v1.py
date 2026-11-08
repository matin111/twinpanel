"""Verified official Xray bootstrap for nodes where github.com returns HTTP 504.

A new Exit can reach api.github.com and raw.githubusercontent.com even when
github.com/XTLS/Xray-core/releases is blocked. Download the official GitHub
release asset through the GitHub Assets API, verify its published SHA256, and
pass the verified archive to XTLS's official install-release.sh --local mode.
Never proxy through the mother, use an unofficial mirror, or replace existing
running Xray binaries on already-configured customer nodes.
"""
from __future__ import annotations

import base64
import shlex

_REMOTE_INSTALL = r'''
import hashlib
import json
import os
import platform
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

BINARY = Path("/usr/local/bin/xray")
SERVICES = (
    Path("/etc/systemd/system/xray.service"),
    Path("/lib/systemd/system/xray.service"),
    Path("/usr/lib/systemd/system/xray.service"),
)
API = "https://api.github.com/repos/XTLS/Xray-core/releases/latest"
ASSET_API = "https://api.github.com/repos/XTLS/Xray-core/releases/assets/"
INSTALL_SCRIPT = "https://raw.githubusercontent.com/XTLS/Xray-install/main/install-release.sh"
HEADERS = {
    "User-Agent": "TwinPanel-Verified-Xray-Install",
    "X-GitHub-Api-Version": "2022-11-28",
}
MAX_ZIP_SIZE = 90 * 1024 * 1024


def download(url, *, accept=None, max_size=MAX_ZIP_SIZE):
    headers = dict(HEADERS)
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    # Some Exit egress networks intermittently return 503/504 even on the
    # official GitHub API. Retry only transport errors with bounded backoff;
    # never bypass the published SHA256 check or use an untrusted mirror.
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=35) as response:
                data = response.read(max_size + 1)
                if len(data) > max_size:
                    raise RuntimeError("XRAY_OFFICIAL_DOWNLOAD_TOO_LARGE")
                return data
        except (urllib.error.URLError, TimeoutError) as exc:
            if isinstance(exc, urllib.error.HTTPError) and exc.code not in (
                429, 500, 502, 503, 504,
            ):
                raise RuntimeError("XRAY_OFFICIAL_REQUEST_REJECTED") from exc
            if attempt == 3:
                raise RuntimeError("XRAY_OFFICIAL_NETWORK_UNAVAILABLE") from exc
            time.sleep(2 ** attempt)


def main():
    # Never unexpectedly upgrade an existing Xray daemon or modify its active
    # customer keys. The normal managed installer owns explicit repair actions.
    if BINARY.is_file() and any(path.is_file() for path in SERVICES):
        print("XRAY_OFFICIAL_BINARY_ALREADY_PRESENT")
        return

    machine = platform.machine().lower()
    asset_name = {
        "x86_64": "Xray-linux-64.zip",
        "amd64": "Xray-linux-64.zip",
        "aarch64": "Xray-linux-arm64-v8a.zip",
        "arm64": "Xray-linux-arm64-v8a.zip",
    }.get(machine)
    if not asset_name:
        raise RuntimeError("XRAY_OFFICIAL_ARCH_UNSUPPORTED")

    data = json.loads(download(
        API, accept="application/vnd.github+json", max_size=2 * 1024 * 1024,
    ))
    if not re.fullmatch(r"v?[0-9]+(?:[.][0-9]+){2}", str(data.get("tag_name") or "")):
        raise RuntimeError("XRAY_OFFICIAL_RELEASE_INVALID")

    matches = [
        row for row in (data.get("assets") or [])
        if isinstance(row, dict) and row.get("name") == asset_name
    ]
    if len(matches) != 1:
        raise RuntimeError("XRAY_OFFICIAL_ASSET_UNAVAILABLE")
    asset = matches[0]
    ident = asset.get("id")
    digest = str(asset.get("digest") or "")
    expected_size = asset.get("size")
    if (
        not isinstance(ident, int) or ident <= 0
        or not isinstance(expected_size, int)
        or not 1024 < expected_size <= MAX_ZIP_SIZE
        or not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", digest)
    ):
        raise RuntimeError("XRAY_OFFICIAL_ASSET_DIGEST_INVALID")

    archive = download(
        ASSET_API + str(ident),
        accept="application/octet-stream",
        max_size=MAX_ZIP_SIZE,
    )
    if len(archive) != expected_size or hashlib.sha256(archive).hexdigest() != digest[7:].lower():
        raise RuntimeError("XRAY_OFFICIAL_ASSET_SHA256_MISMATCH")
    if not archive.startswith(b"PK"):
        raise RuntimeError("XRAY_OFFICIAL_ASSET_NOT_ZIP")

    installer = download(INSTALL_SCRIPT, max_size=256 * 1024)
    if not installer.startswith(b"#!/") or len(installer) < 2048:
        raise RuntimeError("XRAY_OFFICIAL_INSTALLER_INVALID")

    with tempfile.TemporaryDirectory(prefix="twinpanel-verified-xray-") as td:
        root = Path(td)
        archive_path = root / asset_name
        script_path = root / "install-release.sh"
        archive_path.write_bytes(archive)
        script_path.write_bytes(installer)
        os.chmod(script_path, 0o700)
        check = subprocess.run(
            ["bash", "-n", str(script_path)], capture_output=True,
            timeout=15, check=False,
        )
        if check.returncode:
            raise RuntimeError("XRAY_OFFICIAL_INSTALLER_SYNTAX_INVALID")
        installed = subprocess.run(
            ["bash", str(script_path), "install", "--local", str(archive_path)],
            capture_output=True, timeout=360, check=False,
        )
        if installed.returncode:
            # No raw installer output: it may contain remote host details.
            raise RuntimeError("XRAY_OFFICIAL_LOCAL_INSTALL_FAILED")

    if not BINARY.is_file() or not any(path.is_file() for path in SERVICES):
        raise RuntimeError("XRAY_OFFICIAL_INSTALL_INCOMPLETE")
    verify = subprocess.run(
        [str(BINARY), "version"], capture_output=True, timeout=10, check=False,
    )
    if verify.returncode:
        raise RuntimeError("XRAY_OFFICIAL_BINARY_UNUSABLE")
    print("XRAY_OFFICIAL_VERIFIED_LOCAL_INSTALL_OK")


if __name__ == "__main__":
    main()
'''


def official_xray_install_command() -> str:
    # The remote source is Python inside a literal. Validate it explicitly
    # before packaging the SSH command; py_compile of this module is not enough.
    try:
        compile(_REMOTE_INSTALL, "<verified-xray-official-installer>", "exec")
    except SyntaxError as exc:
        raise RuntimeError("XRAY_INSTALL_HELPER_SCRIPT_SYNTAX_INVALID") from exc
    encoded = base64.b64encode(_REMOTE_INSTALL.encode("utf-8")).decode("ascii")
    return "printf '%s' " + shlex.quote(encoded) + " | base64 -d | python3"
