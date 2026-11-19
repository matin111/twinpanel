#!/usr/bin/env python3
"""Fail-closed validation of a locally developer-signed macOS TwinConnect app.

Inspect the *installed build artifact* (app/extension/static linkage), not only
source .entitlements files. This does not start a VPN or verify live traffic.
Run on an Apple-provisioned cloud Mac AFTER building the signed candidate.
"""
from __future__ import annotations

import plistlib
import re
import subprocess
import sys
from pathlib import Path


def fail(reason: str) -> None:
    raise SystemExit("SIGNED_MAC_BUNDLE_INVALID: " + reason)


def run(*command: str) -> bytes:
    proc = subprocess.run(command, capture_output=True, check=False)
    if proc.returncode != 0:
        fail("command failed: " + command[0] + " " + command[1])
    return proc.stdout


def plist(path: Path) -> dict:
    if not path.is_file():
        fail("missing Info.plist: " + str(path))
    try:
        with path.open("rb") as handle:
            value = plistlib.load(handle)
        if not isinstance(value, dict):
            fail("invalid plist")
        return value
    except (OSError, ValueError, plistlib.InvalidFileException):
        fail("unreadable plist: " + str(path))


def signature_team(path: Path) -> str:
    run("codesign", "--verify", "--deep", "--strict", str(path))
    result = subprocess.run(
        ["codesign", "-dv", "--verbose=4", str(path)],
        capture_output=True, check=False,
    )
    if result.returncode != 0:
        fail("signature details unavailable: " + str(path))
    data = (result.stdout + result.stderr).decode("utf-8", "replace")
    match = re.search(r"^TeamIdentifier=([A-Z0-9]{10})$", data, re.MULTILINE)
    if match is None:
        fail("not provisioned with a valid Apple Team: " + str(path))
    return match.group(1)


def effective_entitlements(path: Path) -> dict:
    # Entitlements are extracted from the signature. Do NOT trust the source
    # .entitlements file; a correctly configured source can be signed wrong.
    result = subprocess.run(
        ["codesign", "-d", "--entitlements", ":-", str(path)],
        capture_output=True, check=False,
    )
    if result.returncode != 0:
        fail("cannot read signed entitlements: " + str(path))
    payload = result.stdout
    if not payload.startswith(b"<?xml") and not payload.startswith(b"bplist"):
        fail("signed entitlements not a plist: " + str(path))
    try:
        entitlements = plistlib.loads(payload)
    except (ValueError, plistlib.InvalidFileException):
        fail("signed entitlement plist malformed: " + str(path))
    if not isinstance(entitlements, dict):
        fail("signed entitlement plist malformed: " + str(path))
    return entitlements


def static_libbox_symbols_present(nm_output: str) -> bool:
    """Both Go binding exports must live inside the signed extension binary."""
    required = ("_LibboxSetup", "_LibboxNewCommandServer")
    exported = set()
    for line in nm_output.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            exported.add(parts[-1])
    return all(symbol in exported for symbol in required)


def main() -> None:
    if sys.platform != "darwin":
        fail("must execute on macOS")
    if len(sys.argv) != 2:
        fail("usage: verify_signed_macos_bundle.py /path/to/twinconnect.app")

    app = Path(sys.argv[1]).resolve()
    if not app.is_dir() or app.suffix != ".app":
        fail("application bundle not found")
    extension = app / "Contents/PlugIns/PacketTunnel.appex"
    executable = extension / "Contents/MacOS/PacketTunnel"
    if not extension.is_dir() or not executable.is_file():
        fail("PacketTunnel extension executable missing")
    if (extension / "Contents/Frameworks/Libbox.framework").exists():
        fail("unexpected dynamic Libbox embed; use a static Go archive")
    # A load command is not expected for a statically linked Go archive.
    # Requiring actual exported Libbox symbols prevents a signed bundle
    # marker from being mistaken for proof that the backend was linked.
    symbols = run("nm", "-g", str(executable)).decode("utf-8", "replace")
    if not static_libbox_symbols_present(symbols):
        fail("PacketTunnel executable missing static Libbox binding symbols")

    app_info = plist(app / "Contents/Info.plist")
    extension_info = plist(extension / "Contents/Info.plist")
    if extension_info.get("CFBundleIdentifier") != (
        "com.twinpanel.twinconnect.PacketTunnel"
    ):
        fail("wrong PacketTunnel identifier")
    if extension_info.get("TwinConnectProtocolBackendLinked") is not True:
        fail("Libbox signed test backend marker disabled")
    group = app_info.get("TwinConnectKeychainAccessGroup")
    if not isinstance(group, str) or not re.fullmatch(
        r"[A-Z0-9]{10}\.com\.twinpanel\.twinconnect\.shared", group
    ):
        fail("missing or malformed shared Keychain group")

    teams = [signature_team(path) for path in (app, extension)]
    if len(set(teams)) != 1:
        fail("app and PacketTunnel extension have different signing teams")
    team = teams[0]
    if group != f"{team}.com.twinpanel.twinconnect.shared":
        fail("Keychain group doesn't match Apple signing Team ID")

    for bundle in (app, extension):
        entitlements = effective_entitlements(bundle)
        if "packet-tunnel-provider" not in entitlements.get(
            "com.apple.developer.networking.networkextension", []
        ):
            fail("signed Network Extension entitlement missing")
        if group not in entitlements.get("keychain-access-groups", []):
            fail("signed shared Keychain entitlement missing")
        if entitlements.get("com.apple.security.app-sandbox") is not True:
            fail("signed app sandbox entitlement missing")
        if entitlements.get("com.apple.security.network.client") is not True:
            fail("signed outgoing network entitlement missing")

    print("SIGNED_MAC_BUNDLE_CHECK_PASSED")
    print("APPLE_TEAM_PROVISIONED=YES")
    print("PACKET_TUNNEL_STATIC_LIBBOX_LINKED=YES")
    print("NETWORK_EXTENSION_AND_KEYCHAIN_ENTITLED=YES")
    print("LIVE_TUNNEL_HANDSHAKE_IP_AND_DNS=NOT_VERIFIED")


if __name__ == "__main__":
    main()
