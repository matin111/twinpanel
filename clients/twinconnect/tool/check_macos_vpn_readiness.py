#!/usr/bin/env python3
"""Read-only preflight for macOS system VPN readiness.

Does not launch a VPN, contact the panel, modify routes/DNS/proxies, or read
private connection profiles. Absence of warnings is NOT proof of live egress.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys


def command(*argv: str) -> tuple[int, bytes, bytes]:
    try:
        result = subprocess.run(
            list(argv), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=8, check=False,
        )
        return result.returncode, result.stdout, result.stderr
    except (OSError, subprocess.TimeoutExpired):
        return 127, b"", b""


def info(bundle: Path) -> dict:
    try:
        with (bundle / "Contents/Info.plist").open("rb") as file:
            value = plistlib.load(file)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def signature(bundle: Path) -> dict:
    if not bundle.is_dir():
        return {"valid": False, "team": None, "entitlements": []}
    verified, _, _ = command("/usr/bin/codesign", "--verify", "--strict",
                             str(bundle))
    _, _, details = command("/usr/bin/codesign", "-dv", "--verbose=4",
                            str(bundle))
    decoded = details.decode("utf-8", "replace")
    team_match = re.search(r"^TeamIdentifier=([A-Z0-9]+)$", decoded, re.M)
    team = team_match.group(1) if team_match else None
    entitlement_result, stdout, stderr = command(
        "/usr/bin/codesign", "-d", "--entitlements", ":-", str(bundle))
    entitlements = []
    if entitlement_result == 0:
        payload = stdout + b"\n" + stderr
        first, last = payload.find(b"<plist"), payload.find(b"</plist>")
        if first >= 0 and last > first:
            try:
                values = plistlib.loads(payload[first:last + len(b"</plist>")])
                if isinstance(values, dict):
                    entitlements = values.get(
                        "com.apple.developer.networking.networkextension", [])
                    if not isinstance(entitlements, list):
                        entitlements = []
            except (ValueError, TypeError, plistlib.InvalidFileException):
                pass
    return {"valid": verified == 0 and team is not None,
            "team": team, "entitlements": entitlements}


def discover_app() -> Path | None:
    derived = Path.home() / "Library/Developer/Xcode/DerivedData"
    candidates = []
    for name in ("Runner.app", "twinconnect.app", "TwinConnect.app"):
        candidates.extend(
            x for x in derived.glob("*/Build/Products/Debug/" + name)
            if "Index.noindex" not in str(x)
        )
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def audit(app: Path | None) -> dict:
    if app is None or not app.is_dir():
        return {"result": "APP_NOT_FOUND",
                "next": "Build the app, then pass --app /path/to/Runner.app"}
    extension = app / "Contents/PlugIns/PacketTunnel.appex"
    app_sig = signature(app)
    ext_sig = signature(extension)
    ext_info = info(extension)
    app_info = info(app)
    app_mode = "packet-tunnel-provider" in app_sig["entitlements"]
    ext_mode = "packet-tunnel-provider" in ext_sig["entitlements"]
    team_match = (bool(app_sig["team"]) and
                  app_sig["team"] == ext_sig["team"])
    keychain_group = bool(app_info.get("TwinConnectKeychainAccessGroup"))
    backend_marker = bool(
        ext_info.get("TwinConnectProtocolBackendLinked") or
        ext_info.get("TwinConnectWireGuardBackendLinked"))
    checks = {
        "extension_present": extension.is_dir(),
        "app_apple_team_signature": app_sig["valid"],
        "extension_apple_team_signature": ext_sig["valid"],
        "signing_team_matches": team_match,
        "app_packet_tunnel_entitlement": app_mode,
        "extension_packet_tunnel_entitlement": ext_mode,
        "shared_keychain_group_configured": keychain_group,
        "extension_declares_linked_backend": backend_marker,
    }
    permitted = all(checks.values())
    return {
        "result": ("SIGNING_PREREQUISITES_PRESENT_BACKEND_UNVERIFIED"
                   if permitted else "SYSTEM_VPN_NOT_READY"),
        "app": str(app),
        "checks": checks,
        "missing": [key for key, ok in checks.items() if not ok],
        "next": ("Verify backend symbols and real egress on a signed test Mac"
                 if permitted else
                 "Provision and sign Runner and PacketTunnel with matching "
                 "Apple Network Extension entitlements; link the VPN engine"),
        "internet_settings_modified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, help="Exact Runner.app path")
    args = parser.parse_args()
    report = audit(args.app if args.app else discover_app())
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
