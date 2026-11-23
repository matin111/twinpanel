#!/usr/bin/env python3
"""Unsigned Mieru macOS preflight: validated local core + TUN relay candidate.

This module does not start a VPN, write credentials, install routes, or use
NetworkExtension. Actual connection needs the native client process, verified
upstream bypass and the existing root-owned TUN controller.
"""
from __future__ import annotations

import copy
import ipaddress
import json
from typing import Any

LOCAL_SOCKS_PORT = 17091
MAX_CONFIG_BYTES = 131072
VALID_BIND_PROTOCOLS = {"TCP", "UDP"}
ALLOWED_HANDSHAKE = {"HANDSHAKE_STANDARD", "HANDSHAKE_NO_WAIT"}


def prepare_unsigned_profile(panel_config: dict[str, Any]) -> tuple[dict, dict]:
    """Fail closed if the panel's account-scoped Mieru profile is unsuitable.

    Returns a native Mieru configuration for an isolated local SOCKS listener
    and a separate sing-box candidate. Neither is a running connection.
    """
    if not isinstance(panel_config, dict):
        raise ValueError("MIERU_CONFIG_INVALID")
    if len(json.dumps(panel_config).encode("utf-8")) > MAX_CONFIG_BYTES:
        raise ValueError("MIERU_CONFIG_TOO_LARGE")
    profiles = panel_config.get("profiles")
    if not isinstance(profiles, list) or len(profiles) != 1:
        raise ValueError("MIERU_EXACTLY_ONE_PROFILE_REQUIRED")
    profile = profiles[0]
    if not isinstance(profile, dict):
        raise ValueError("MIERU_PROFILE_INVALID")
    identity = profile.get("profileName")
    user = profile.get("user")
    if not isinstance(identity, str) or not 1 <= len(identity) <= 128:
        raise ValueError("MIERU_ACCOUNT_INVALID")
    if panel_config.get("activeProfile") != identity:
        raise ValueError("MIERU_ACTIVE_PROFILE_MISMATCH")
    if not isinstance(user, dict) or user.get("name") != identity:
        raise ValueError("MIERU_USER_INVALID")
    pw = user.get("password")
    if not isinstance(pw, str) or not 1 <= len(pw.encode("utf-8")) <= 4096:
        raise ValueError("MIERU_CREDENTIAL_MISSING")
    if panel_config.get("socks5ListenLAN") is not False:
        raise ValueError("MIERU_LAN_PROXY_NOT_ALLOWED")
    if panel_config.get("httpProxyListenLAN") is not False:
        raise ValueError("MIERU_HTTP_PROXY_NOT_ALLOWED")
    if panel_config.get("socks5Authentication"):
        raise ValueError("MIERU_LOOPBACK_AUTH_UNEXPECTED")
    if panel_config.get("profiles") != [profile]:
        raise ValueError("MIERU_PROFILE_AMBIGUOUS")
    if not isinstance(panel_config.get("socks5Port"), int) or (
            isinstance(panel_config.get("socks5Port"), bool)):
        raise ValueError("MIERU_SOCKS_PORT_INVALID")
    servers = profile.get("servers")
    if not isinstance(servers, list) or len(servers) != 1:
        raise ValueError("MIERU_EXACTLY_ONE_SERVER_REQUIRED")
    endpoint = servers[0]
    if not isinstance(endpoint, dict):
        raise ValueError("MIERU_SERVER_INVALID")
    try:
        public = ipaddress.IPv4Address(endpoint.get("ipAddress"))
        if not public.is_global:
            raise ValueError
    except (ValueError, TypeError, ipaddress.AddressValueError):
        raise ValueError("MIERU_PUBLIC_IPV4_REQUIRED") from None
    # Mieru is not TLS-based. Pin the authenticated server to a literal
    # public IPv4 rather than letting DNS resolution leak/change the path.
    domain = endpoint.get("domainName")
    if domain is not None and (not isinstance(domain, str) or len(domain) > 255):
        raise ValueError("MIERU_DOMAIN_INVALID")
    ports = endpoint.get("portBindings")
    if not isinstance(ports, list) or not 1 <= len(ports) <= 32:
        raise ValueError("MIERU_BINDINGS_INVALID")
    seen = set()
    for binding in ports:
        if not isinstance(binding, dict) or binding.get("protocol") not in VALID_BIND_PROTOCOLS:
            raise ValueError("MIERU_BINDINGS_INVALID")
        port = binding.get("port")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("MIERU_PORT_INVALID")
        k = (binding["protocol"], port)
        if k in seen:
            raise ValueError("MIERU_DUPLICATE_BINDINGS")
        seen.add(k)
    native = copy.deepcopy(panel_config)
    native["profiles"][0]["servers"][0]["domainName"] = ""
    native["rpcPort"] = 0
    native.pop("httpProxyPort", None)
    native["httpProxyListenLAN"] = False
    native["socks5ListenLAN"] = False
    native["socks5Port"] = LOCAL_SOCKS_PORT
    native.pop("socks5Authentication", None)
    # System routing stays with the EXISTING root-owned TUN controller.
    # Never add a caller-supplied bypass or a direct fallback.
    tun = {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "tun", "tag": "twinconnect-tun",
            "address": ["172.19.0.1/30"], "auto_route": True,
            "auto_redirect": False, "strict_route": False, "stack": "system"
        }],
        "outbounds": [{
            "type": "socks", "tag": "proxy", "server": "127.0.0.1",
            "server_port": LOCAL_SOCKS_PORT, "version": "5",
            "network": "tcp"
        }],
        "route": {"final": "proxy", "auto_detect_interface": True}
    }
    return native, tun


def safe_preflight_summary(config: dict[str, Any]) -> dict:
    core, _ = prepare_unsigned_profile(config)
    return {
        "state": "profile_preflight_only",
        "apple_code_signing_required": False,
        "local_proxy_port": core["socks5Port"],
        "profile_valid": True,
        "native_core_started": False,
        "system_tun_started": False,
        "tunnel_connected": False,
        "reason": "MIERU_UNSIGNED_CORE_AND_UPSTREAM_ROUTE_NOT_YET_VERIFIED",
    }


def main() -> int:
    import sys
    try:
        data = sys.stdin.buffer.read(MAX_CONFIG_BYTES + 1)
        if len(data) > MAX_CONFIG_BYTES:
            raise ValueError("MIERU_CONFIG_TOO_LARGE")
        summary = safe_preflight_summary(json.loads(data))
    except (UnicodeError, ValueError, TypeError) as exc:
        code = str(exc)
        if not code.startswith("MIERU_") or not code.isupper():
            code = "MIERU_CONFIG_INVALID"
        print(json.dumps({"state": "rejected", "reason": code}))
        return 2
    print(json.dumps(summary, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())