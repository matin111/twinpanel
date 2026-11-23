#!/usr/bin/env python3
"""Read-only L2TP/IPsec profile and native service readiness check for macOS.

Never starts a VPN, writes credentials, creates a network service or changes
routes/DNS. Only the chosen, authenticated panel profile may be passed in.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import subprocess
import sys

MAX_BYTES = 4096
MAX_SECRET_BYTES = 256


def inspect_profile(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("L2TP_PROFILE_NOT_OBJECT")
    if set(value) != {"server", "username", "password", "psk"}:
        raise ValueError("L2TP_PROFILE_FIELDS_INVALID")
    host = value["server"]
    if not isinstance(host, str) or not re.fullmatch(r"[a-zA-Z0-9.-]{1,253}", host):
        raise ValueError("L2TP_ENDPOINT_INVALID")
    if host.startswith("-") or host.endswith(".") or ".." in host:
        raise ValueError("L2TP_ENDPOINT_INVALID")
    try:
        address = ipaddress.ip_address(host)
        if not isinstance(address, ipaddress.IPv4Address) or not address.is_global:
            raise ValueError("L2TP_ENDPOINT_NOT_PUBLIC")
    except ValueError as exc:
        if str(exc) == "L2TP_ENDPOINT_NOT_PUBLIC":
            raise
        # DNS validation happens at connection time.
        pass
    for key in ("username", "password", "psk"):
        secret = value[key]
        if not isinstance(secret, str) or not 1 <= len(secret.encode("utf-8")) <= MAX_SECRET_BYTES:
            raise ValueError("L2TP_CREDENTIALS_INVALID")
        if re.search(r"[\x00-\x1f\x7f]", secret):
            raise ValueError("L2TP_CREDENTIALS_INVALID")
    return {"state": "reviewed",
            "credentials_validated": True,
            "connection_active": False}


def native_service_check() -> dict:
    if sys.platform != "darwin":
        raise ValueError("L2TP_MACOS_REQUIRED")
    # Do not permit the native stack to replace management networking while
    # another system VPN is active, even though this probe itself is read-only.
    try:
        report = subprocess.run(["/usr/sbin/scutil", "--nc", "list"],
                                capture_output=True, text=True, timeout=8,
                                check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("L2TP_NATIVE_SERVICE_CHECK_FAILED") from None
    if report.returncode or len(report.stdout) > 8192:
        raise ValueError("L2TP_NATIVE_SERVICE_CHECK_FAILED")
    # Exact name reserved for an independently verified L2TP service.
    matches = [line for line in report.stdout.splitlines()
               if re.search(r'"TwinConnect L2TP"(?=\s|$)', line)]
    return {"state": "preflight",
            "native_service_available": len(matches) == 1,
            "connection_active": False,
            "reason": ("L2TP_NATIVE_SERVICE_READY" if len(matches) == 1 else
                       "L2TP_NATIVE_SERVICE_NOT_CONFIGURED")}


def main() -> int:
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in ("capabilities", "review"):
            raise ValueError("L2TP_OPERATION_NOT_ALLOWED")
        if sys.argv[1] == "capabilities":
            print(json.dumps(native_service_check()))
            return 0
        data = os.read(0, MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("L2TP_PROFILE_TOO_LARGE")
        outcome = inspect_profile(json.loads(data))
        outcome["native_service"] = native_service_check()["reason"]
        print(json.dumps(outcome))
        return 0
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        reason = str(exc)
        if not re.fullmatch(r"L2TP_[A-Z0-9_]{4,70}", reason):
            reason = "L2TP_PREFLIGHT_FAILED"
        print(json.dumps({"state": "error", "reason": reason,
                          "connection_active": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
