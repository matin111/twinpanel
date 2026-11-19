#!/usr/bin/env python3
"""Read-only host preflight for TwinConnect macOS development.

Run from anywhere: python3 clients/twinconnect/macos_native/preflight_macos.py
No credentials, provisioning profiles, project files, or network requests are read.
This checks local prerequisites; it does NOT verify a VPN connection.
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path


def command_output(*args: str, timeout: int = 25) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout, check=False,
        )
        return completed.returncode, completed.stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, type(exc).__name__


def metal_available() -> tuple[bool, str]:
    """Check for a usable MTLDevice, not just a reported graphics adapter."""
    swift = shutil.which("swift") or "/usr/bin/swift"
    code = (
        'import Metal; '
        'if let device = MTLCreateSystemDefaultDevice() { '
        'print("TWINCONNECT_METAL_AVAILABLE") '
        '} else { print("TWINCONNECT_METAL_UNAVAILABLE") }'
    )
    status, output = command_output(swift, "-e", code, timeout=65)
    if status == 0 and "TWINCONNECT_METAL_AVAILABLE" in output:
        return True, "Metal device available"
    if status == 0 and "TWINCONNECT_METAL_UNAVAILABLE" in output:
        return False, "No usable Metal device: Flutter macOS GUI cannot render here"
    return False, "Could not verify Metal availability: " + output[-300:]


def xcode_status() -> tuple[bool, str]:
    status, output = command_output("xcodebuild", "-version")
    match = re.search(r"^Xcode\s+(\d+)(?:\.(\d+))?", output, re.MULTILINE)
    if status != 0 or not match:
        return False, "Xcode not available: " + output[-180:]
    major = int(match.group(1))
    return major >= 16, output.splitlines()[0] + (
        " (project requires Xcode 16+)" if major < 16 else ""
    )


def signing_status() -> tuple[bool, str]:
    # List identities only; never disclose certificates, IDs, or secrets.
    status, output = command_output("security", "find-identity", "-v", "-p", "codesigning")
    if status != 0:
        return False, "Unable to inspect local code-signing identities"
    match = re.search(r"(\d+) valid identities found", output)
    count = int(match.group(1)) if match else 0
    if not count:
        return False, "No valid code-signing identity found"
    return True, f"{count} code-signing identity/identities found (Network Extension entitlement still unverified)"


def check_host() -> dict[str, object]:
    is_mac = platform.system() == "Darwin"
    if not is_mac:
        return {"host": "not macOS", "gui_ready": False, "signed_vpn_build_ready": False,
                "checks": {"macos": {"ok": False, "detail": "Run on macOS"}}}

    metal_ok, metal_text = metal_available()
    xcode_ok, xcode_text = xcode_status()
    sign_ok, sign_text = signing_status()
    checks = {
        "metal": {"ok": metal_ok, "detail": metal_text},
        "xcode": {"ok": xcode_ok, "detail": xcode_text},
        "codesigning": {"ok": sign_ok, "detail": sign_text},
        "cocoapods": {"ok": shutil.which("pod") is not None,
                      "detail": "pod executable found" if shutil.which("pod") else "CocoaPods not in PATH"},
        "flutter": {"ok": shutil.which("flutter") is not None,
                    "detail": "flutter executable found" if shutil.which("flutter") else "Flutter not in PATH"},
    }
    return {
        "host": "macOS",
        "gui_ready": metal_ok,
        "signed_vpn_build_ready": xcode_ok and sign_ok,
        "checks": checks,
        "note": "A valid packet-tunnel-provider entitlement and live VPN traffic are not verified by this script.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print machine-readable checks")
    args = parser.parse_args()
    result = check_host()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("TwinConnect macOS host preflight (read-only)")
        for name, value in result["checks"].items():
            print(f"[{'OK' if value['ok'] else 'BLOCKED'}] {name}: {value['detail']}")
        if result.get("note"):
            print(result["note"])
        if not result["gui_ready"]:
            print("GUI testing requires a Mac exposing a real Metal device; rebuilding Flutter will not fix this.")
        if not result["signed_vpn_build_ready"]:
            print("Signed PacketTunnel testing needs Xcode 16+ and an entitled Apple signing identity.")
    return 0  # Diagnostic report: blocked hosts are not a script execution error.


if __name__ == "__main__":
    sys.exit(main())
