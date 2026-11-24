#!/usr/bin/env python3
"""Cisco / AnyConnect authentication-only preflight for unsigned TwinConnect macOS.

Reads one short JSON profile on stdin. No routes, TUN, DNS or system proxy are
created. OpenConnect prints a sensitive login cookie on successful --authenticate:
capture it in memory, verify it exists, and NEVER echo or persist that cookie.
"""
from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys

BINARIES = (
    "/opt/homebrew/bin/openconnect",
    "/usr/local/bin/openconnect",
    "/opt/local/bin/openconnect",
    "/usr/bin/openconnect",
)
FIELDS = frozenset({"protocol", "host", "port", "username", "password", "servercert"})
SERVERCERT = re.compile(
    r"(?:sha256:[0-9a-fA-F]{64}|pin-sha256:[A-Za-z0-9+/]{43}=)\Z")
USER = re.compile(r"[^\x00-\x1f\x7f]{1,256}\Z")
DOMAIN_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z")
COOKIE = re.compile(rb"(?m)^COOKIE=['\"]?([^\r\n'\"]+)['\"]?\r?$")


def reject(reason: str) -> None:
    raise ValueError(reason)


def public_host(value: str) -> bool:
    if not isinstance(value, str) or not 3 <= len(value) <= 253:
        return False
    if any(char.isspace() for char in value):
        return False
    if any(char in value for char in "@:/\\%?&#"):
        return False
    try:
        return ipaddress.ip_address(value).is_global
    except ValueError:
        pass
    if value.endswith(".") or value.startswith(".") or ".." in value:
        return False
    parts = value.split(".")
    if len(parts) < 2 or not all(DOMAIN_LABEL.fullmatch(p) for p in parts):
        return False
    if parts[-1].lower() in {"local", "internal", "localhost", "invalid", "test"}:
        return False
    return any(c.isalpha() for c in value)


def validate(raw: bytes) -> dict:
    if not raw or len(raw) > 16384:
        reject("CISCO_PROFILE_SIZE_INVALID")
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        reject("CISCO_PROFILE_INVALID_JSON")
    if not isinstance(value, dict) or set(value) - FIELDS:
        reject("CISCO_PROFILE_INVALID")
    if value.get("protocol") != "cisco":
        reject("CISCO_PROTOCOL_MISMATCH")
    host, port = value.get("host"), value.get("port")
    if not public_host(host) or type(port) is not int or not 1 <= port <= 65535:
        reject("CISCO_ENDPOINT_UNSAFE")
    username, password = value.get("username"), value.get("password")
    if not isinstance(username, str) or not USER.fullmatch(username) or username.startswith("-"):
        reject("CISCO_USERNAME_INVALID")
    if not isinstance(password, str) or not 1 <= len(password) <= 4096 or any(
        x in password for x in "\r\n\x00"
    ):
        reject("CISCO_PASSWORD_INVALID")
    pin = value.get("servercert")
    if pin is not None and (not isinstance(pin, str) or not SERVERCERT.fullmatch(pin)):
        reject("CISCO_CERT_PIN_INVALID")
    return value


def binary() -> str | None:
    for name in BINARIES:
        path = Path(name)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def authenticate(profile: dict) -> dict:
    exe = binary()
    if exe is None:
        reject("OPENCONNECT_BINARY_NOT_INSTALLED")
    # --authenticate never creates a tunnel. Password goes to stdin, not argv.
    cmd = [
        exe, "--protocol=anyconnect", "--authenticate", "--non-inter",
        "--no-proxy", "--passwd-on-stdin", "--user=" + profile["username"],
    ]
    if profile.get("servercert"):
        cmd.extend(["--servercert=" + profile["servercert"]])
    cmd.append("https://" + profile["host"] + ":" + str(profile["port"]))
    try:
        reply = subprocess.run(
            cmd, input=(profile["password"] + "\n").encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=40,
        )
    except subprocess.TimeoutExpired:
        reject("CISCO_AUTH_TIMEOUT")
    except OSError:
        reject("OPENCONNECT_EXECUTION_FAILED")
    # stderr may contain gateway URLs, user names or challenge text. Never
    # return, persist or log any of that. Categorize only known phrases.
    if reply.returncode != 0:
        diagnostic = reply.stderr.lower()[-65536:]
        if b"certificate" in diagnostic or b"servercert" in diagnostic:
            reject("CISCO_TLS_CERTIFICATE_FAILED")
        if b"failed to authenticate" in diagnostic or b"authentication failed" in diagnostic:
            reject("CISCO_AUTH_REJECTED")
        if b"non-interactive" in diagnostic or b"interact" in diagnostic:
            reject("CISCO_INTERACTIVE_AUTH_REQUIRED")
        if b"resolve" in diagnostic or b"no such host" in diagnostic:
            reject("CISCO_DNS_FAILED")
        reject("CISCO_AUTH_UNSUCCESSFUL")
    if not COOKIE.search(reply.stdout[:65536]):
        reject("CISCO_AUTH_COOKIE_NOT_RETURNED")
    return {
        "state": "cisco_authentication_verified",
        "protocol": "cisco",
        "vpn_connected": False,
        "tun_created": False,
        "message": "Cisco authentication only; no VPN tunnel or system route",
    }


def main() -> int:
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in {"validate", "authenticate"}:
            reject("CISCO_INVALID_ACTION")
        # Read from stdin only. No profile file, credentials or cookie on disk.
        profile = validate(sys.stdin.buffer.read(16385))
        result = (authenticate(profile) if sys.argv[1] == "authenticate"
                  else {"state": "cisco_profile_valid", "protocol": "cisco",
                        "vpn_connected": False})
        print(json.dumps(result, separators=(",", ":")))
        return 0
    except (ValueError, OSError):
        code = str(sys.exc_info()[1])
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", code):
            code = "CISCO_PREFLIGHT_FAILED"
        print(json.dumps({"state": "error", "reason": code,
                          "vpn_connected": False}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
