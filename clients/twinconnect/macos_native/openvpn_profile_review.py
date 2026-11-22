#!/usr/bin/env python3
"""Bounded OpenVPN client profile review for TwinConnect macOS.

No connection, network change or privilege escalation. An untrusted .ovpn
profile is never passed directly to a root-running OpenVPN process.
The backend must explicitly supply any inline keys; unsupported options fail.
"""
from __future__ import annotations
import ipaddress
import re
import shlex
import json
import sys

MAX_PROFILE_BYTES = 65536
MAX_LINES = 512
MAX_INLINE_BYTES = 32768
# Keep runtime-specific route and credentials out of supplied client options.
ALLOWED_SINGLE = {"client", "nobind", "persist-key", "persist-tun",
                  "auth-nocache", "remote-random",
                  "pull", "float"}
ALLOWED_VALUE = {
    "remote-cert-tls": {"server"},
    "proto": {"udp", "tcp", "tcp-client", "udp4", "tcp4-client"},
    "dev": {"tun"},
    "auth": {"SHA256", "SHA384", "SHA512"},
    "cipher": {"AES-256-GCM", "AES-128-GCM"},
    "tls-version-min": {"1.2", "1.3"},
    "auth-retry": {"none", "nointeract"},
}
ALLOWED_STRING = {"remote", "verify-x509-name", "data-ciphers", "tls-cipher",
                  "tls-ciphersuites"}
FORBIDDEN = {"up", "down", "route-up", "route-pre-down", "learn-address",
             "ipchange", "client-connect", "client-disconnect", "plugin",
             "script-security", "user", "group", "management", "management-client",
             "management-query-passwords", "route",
             "route-ipv6", "dhcp-option", "setenv", "setenv-safe",
             "askpass", "auth-user-pass", "auth-token", "secret",
             "tls-verify", "config", "include", "cd", "chroot",
             "daemon", "writepid", "log", "log-append", "status",
             "ifconfig", "ifconfig-ipv6", "route-delay", "route-method",
             "route-nopull", "pull-filter", "iproute", "dev-node",
             "local", "port", "lport", "http-proxy", "socks-proxy",
             "http-proxy-user-pass", "pkcs11-providers", "pkcs11-id",
             "tls-crypt-v2", "tls-auth", "key-direction"}
INLINE_TAGS = {"ca", "cert", "key", "tls-crypt"}
# Standard TwinPanel export contains redirect-gateway def1. It MUST be
# removed for an unrouted candidate, never forwarded to the engine.
STRIP_LOCAL_DEFAULT_ROUTE = {"redirect-gateway": {("def1",), ("def1", "bypass-dhcp")}}
# Conservative transport controls for existing generated OpenVPN profiles.
BOUNDED_NUMBERS = {
    "tun-mtu": (576, 9000),
    "mssfix": (0, 9000),
    "verb": (0, 4),
}



def review(text: str) -> dict:
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_PROFILE_BYTES:
        raise ValueError("OVPN_PROFILE_TOO_LARGE")
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        raise ValueError("OVPN_TOO_MANY_LINES")
    if "\x00" in text or "\r" in text:
        raise ValueError("OVPN_CONTROL_CHARACTERS")
    cleaned = []
    inline = {}
    active = None
    buffer = []
    seen = set()
    remotes = 0
    stripped = []
    for line in lines:
        item = line.strip()
        if active is not None:
            if item == "</" + active + ">":
                payload = "\n".join(buffer) + "\n"
                if not payload.strip() or len(payload.encode("utf-8")) > MAX_INLINE_BYTES:
                    raise ValueError("OVPN_INLINE_INVALID")
                inline[active] = payload
                active = None
                buffer = []
            elif item.startswith("<") or item.endswith(">"):
                raise ValueError("OVPN_NESTED_INLINE_FORBIDDEN")
            else:
                buffer.append(line)
            continue
        if not item or item.startswith(("#", ";")):
            continue
        if item.startswith("<") and item.endswith(">"):
            name = item[1:-1]
            if name not in INLINE_TAGS or name in inline or name in seen:
                raise ValueError("OVPN_INLINE_NOT_ALLOWED")
            seen.add(name)
            active = name
            continue
        if item.startswith("<"):
            raise ValueError("OVPN_INLINE_UNCLOSED")
        try:
            tokens = shlex.split(item, comments=False, posix=True)
        except ValueError:
            raise ValueError("OVPN_INVALID_DIRECTIVE")
        if not tokens:
            continue
        directive, values = tokens[0].lower(), tokens[1:]
        if not re.fullmatch(r"[a-z][a-z0-9-]*", directive):
            raise ValueError("OVPN_INVALID_DIRECTIVE")
        if directive in STRIP_LOCAL_DEFAULT_ROUTE:
            if tuple(values) not in STRIP_LOCAL_DEFAULT_ROUTE[directive]:
                raise ValueError("OVPN_UNSAFE_DIRECTIVE")
            if directive in seen:
                raise ValueError("OVPN_INVALID_VALUE")
            seen.add(directive)
            stripped.append(directive)
            continue
        if directive in FORBIDDEN or directive.startswith("route-"):
            raise ValueError("OVPN_UNSAFE_DIRECTIVE")
        if directive in ALLOWED_SINGLE:
            if values or directive in seen:
                raise ValueError("OVPN_INVALID_FLAG")
        elif directive in ALLOWED_VALUE:
            if len(values) != 1 or values[0] not in ALLOWED_VALUE[directive] or directive in seen:
                raise ValueError("OVPN_INVALID_VALUE")
        elif directive in BOUNDED_NUMBERS:
            low, high = BOUNDED_NUMBERS[directive]
            if len(values) != 1 or directive in seen or not values[0].isdigit() or not (low <= int(values[0]) <= high):
                raise ValueError("OVPN_INVALID_VALUE")
        elif directive == "resolv-retry":
            if len(values) != 1 or directive in seen or not (
                    values[0] == "infinite" or
                    (values[0].isdigit() and 1 <= int(values[0]) <= 600)):
                raise ValueError("OVPN_INVALID_VALUE")
        elif directive == "remote":
            if len(values) not in (1, 2, 3) or remotes >= 8:
                raise ValueError("OVPN_INVALID_REMOTE")
            host = values[0]
            try:
                parsed = ipaddress.ip_address(host)
                valid_host = parsed.is_global
            except ValueError:
                valid_host = bool(re.fullmatch(
                    r"(?=.{4,253}$)[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", host))
            if not valid_host or (len(values) > 1 and (
                    not values[1].isdigit() or not 1 <= int(values[1]) <= 65535)):
                raise ValueError("OVPN_INVALID_REMOTE")
            if len(values) == 3 and values[2] not in ("udp", "tcp", "tcp-client"):
                raise ValueError("OVPN_INVALID_REMOTE")
            remotes += 1
        elif directive in ALLOWED_STRING:
            if not 1 <= len(values) <= 3 or directive in seen or any(
                    not 0 < len(value) <= 512 or any(c in value for c in "\n\r\x00")
                    for value in values):
                raise ValueError("OVPN_INVALID_STRING")
        else:
            raise ValueError("OVPN_UNREVIEWED_DIRECTIVE")
        if directive != "remote":
            seen.add(directive)
        # Reconstruct tokens; the source file is never used for engine startup.
        cleaned.append(" ".join(shlex.quote(token) for token in tokens))
    if active is not None or not remotes or "ca" not in inline:
        raise ValueError("OVPN_INCOMPLETE_PROFILE")
    return {"state": "reviewed_unrouted_candidate",
            "directives": cleaned, "inline": inline, "remotes": remotes,
            "connected": False, "route_changed": False,
            "stripped": stripped}

def main() -> int:
    """Review a private stdin profile. Print no credentials or destinations."""
    raw = sys.stdin.buffer.read(MAX_PROFILE_BYTES + 1)
    if not raw or len(raw) > MAX_PROFILE_BYTES:
        print(json.dumps({"state": "rejected"}))
        return 1
    try:
        reviewed = review(raw.decode("utf-8", errors="strict"))
    except (ValueError, UnicodeError):
        print(json.dumps({"state": "rejected"}))
        return 1
    print(json.dumps({
        "state": reviewed["state"], "connected": False,
        "route_changed": False, "remotes": reviewed["remotes"]
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
