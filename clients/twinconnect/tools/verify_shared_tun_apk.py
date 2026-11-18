#!/usr/bin/env python3
"""Fail release builds when Android advertises more than one VPN owner.

This inspects the compiled APK manifest, after Android has merged every
Flutter plugin manifest. Source-manifest grep cannot detect an upstream AAR
silently registering another VpnService.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


EXPECTED_SERVICE = "com.twinpanel.twinconnect.SharedTunVpnService"
VPN_ACTION = "android.net.VpnService"
VPN_PERMISSION = "android.permission.BIND_VPN_SERVICE"


def aapt_binary() -> str:
    found = shutil.which("aapt")
    if found:
        return found
    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        sdk = os.environ.get(variable)
        if not sdk:
            continue
        candidates = sorted((Path(sdk) / "build-tools").glob("*/aapt"), reverse=True)
        if candidates:
            return str(candidates[0])
    raise RuntimeError("Android SDK aapt is required to verify the packaged manifest")


def manifest_services(tree: str) -> list[dict[str, str | bool]]:
    """Extract attributes/actions from aapt's indented binary XML dump."""
    services: list[dict[str, str | bool]] = []
    current: dict[str, str | bool] | None = None
    service_indent = -1
    for line in tree.splitlines():
        element = re.match(r"^(\s*)E:\s+([\w-]+)(?:\s|$)", line)
        if element:
            indent = len(element.group(1))
            if current is not None and indent <= service_indent:
                services.append(current)
                current = None
            if element.group(2) == "service":
                current = {"name": "", "permission": "", "exported": False, "vpn_action": False}
                service_indent = indent
            continue
        if current is None:
            continue
        attribute = re.match(r"^(\s*)A:\s+android:(name|permission|exported)\b.*?=(.*)$", line)
        if attribute is None:
            continue
        indent, key, value = len(attribute.group(1)), attribute.group(2), attribute.group(3)
        if key == "name" and VPN_ACTION in value and re.search(r'android\.net\.VpnService"', value):
            current["vpn_action"] = True
        if indent <= service_indent + 2:
            if key in ("name", "permission"):
                match = re.search(r'"([^"]+)"', value)
                if match:
                    current[key] = match.group(1)
            elif key == "exported":
                current["exported"] = bool(re.search(
                    r'"true"|\(type 0x12\)0xffffffff|\(type 0x12\)0x1\b', value,
                    re.IGNORECASE,
                ))
    if current is not None:
        services.append(current)
    return services


def verify(tree: str) -> None:
    services = manifest_services(tree)
    owners = [service for service in services if service["vpn_action"]]
    if len(owners) != 1:
        raise RuntimeError(
            f"Expected one discoverable Android VPN service, got {len(owners)}: "
            f"{[service['name'] for service in owners]}"
        )
    sole = owners[0]
    if sole["name"] not in (EXPECTED_SERVICE, ".SharedTunVpnService"):
        raise RuntimeError(f"Wrong Android VPN owner: {sole['name']}")
    if sole["permission"] != VPN_PERMISSION:
        raise RuntimeError("Shared VPN owner lacks android.permission.BIND_VPN_SERVICE")
    if sole["exported"] is not True:
        raise RuntimeError("Shared VPN owner is not exported to the Android system")
    print(f"Verified single OS-discoverable shared VPN owner: {sole['name']}")


def main(apks: list[str]) -> None:
    if not apks:
        raise RuntimeError("Supply at least one APK path")
    aapt = aapt_binary()
    for filename in apks:
        path = Path(filename)
        if not path.is_file():
            raise RuntimeError(f"Missing release APK: {path}")
        output = subprocess.run(
            [aapt, "dump", "xmltree", str(path), "AndroidManifest.xml"],
            check=True, text=True, capture_output=True, timeout=45,
        ).stdout
        verify(output)
        print(f"Checked {path}")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print(f"Unsafe Android APK manifest: {error}", file=sys.stderr)
        sys.exit(1)
