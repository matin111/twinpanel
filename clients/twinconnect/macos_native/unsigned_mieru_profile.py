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
import re
import subprocess
from typing import Any

LOCAL_SOCKS_PORT = 17091
MAX_CONFIG_BYTES = 131072
VALID_BIND_PROTOCOLS = {"TCP", "UDP"}
ALLOWED_HANDSHAKE = {"HANDSHAKE_STANDARD", "HANDSHAKE_NO_WAIT"}


def resolve_authenticated_ingress_domain(hostname: str) -> str:
    """Pin the panel-authorized Iran ingress DNS before activating any TUN.

    The panel may deliver a modern Iran->Exit Mieru endpoint as domainName,
    with ipAddress deliberately empty. Falling back to the Exit probe IP
    corrupts the tunnel binding (35000+node_id) and never reaches Iran NAT.
    Only resolve a well-formed public hostname from the authenticated
    subscription profile; refuse private, loopback, or DNS-less endpoints.
    """
    if not isinstance(hostname, str) or not re.fullmatch(
            r"(?=.{4,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}",
            hostname):
        raise ValueError("MIERU_INGRESS_DOMAIN_INVALID")
    try:
        result = subprocess.run(
            ["/usr/bin/dig", "+short", "+time=2", "+tries=1",
             "-t", "A", hostname],
            capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("MIERU_INGRESS_DNS_UNAVAILABLE") from None
    if result.returncode != 0 or len(result.stdout) > 4096:
        raise ValueError("MIERU_INGRESS_DNS_UNAVAILABLE")
    resolved = []
    for value in result.stdout.splitlines():
        try:
            ip = ipaddress.IPv4Address(value.strip())
            if ip.is_global:
                resolved.append(str(ip))
        except ipaddress.AddressValueError:
            # Ignore CNAME lines; never treat them as a second destination.
            continue
    if not resolved or len(set(resolved)) > 8:
        raise ValueError("MIERU_INGRESS_PUBLIC_IPV4_REQUIRED")
    return sorted(set(resolved), key=lambda value: bytes(
        int(part) for part in value.split(".")))[0]


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
    domain = endpoint.get("domainName")
    raw_ip = endpoint.get("ipAddress")
    if raw_ip is None or raw_ip == "":
        # The delivered modern ingress uses an authenticated domain. Resolve
        # BEFORE starting TUN and pin to that ingress, never to the Exit node.
        public_ip = resolve_authenticated_ingress_domain(domain)
    else:
        try:
            public = ipaddress.IPv4Address(raw_ip)
            if not public.is_global:
                raise ValueError
            public_ip = str(public)
        except (ValueError, TypeError, ipaddress.AddressValueError):
            # An explicit private/malformed IP is not a reason to silently
            # switch over to an unrelated hostname.
            raise ValueError("MIERU_PUBLIC_IPV4_REQUIRED") from None
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
    native["profiles"][0]["servers"][0]["ipAddress"] = public_ip
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


def prepare_mbox_tun(panel_config: dict[str, Any]) -> dict:
    """Review the current profile into an unsigned mbox Mieru native TUN.

    Separate root-owned engine: existing sing-box remains untouched.
    A direct Mieru outbound avoids loopback SOCKS and endpoint route recursion.
    Credentials only leave memory in the authenticated root TUN socket.
    """
    native, _ = prepare_unsigned_profile(panel_config)
    profile = native["profiles"][0]
    endpoint = profile["servers"][0]
    selected = [x for x in endpoint["portBindings"]
                if x.get("protocol") == "TCP"]
    if not selected:
        raise ValueError("MIERU_TCP_BINDING_REQUIRED")
    if profile.get("handshakeMode") not in (
            None, "HANDSHAKE_STANDARD"):
        raise ValueError("MIERU_UNSUPPORTED_HANDSHAKE")
    multiplex = profile.get("multiplexing")
    if multiplex is not None and multiplex != {"level": "MULTIPLEXING_LOW"}:
        raise ValueError("MIERU_UNSUPPORTED_MULTIPLEXING")
    if profile.get("mtu") not in (None, 1400):
        raise ValueError("MIERU_UNSUPPORTED_MTU")
    out = {
        "type": "mieru", "tag": "proxy",
        "server": endpoint["ipAddress"],
        "server_port": selected[0]["port"],
        "transport": "TCP",
        "username": profile["user"]["name"],
        "password": profile["user"]["password"],
    }
    # Isolated native mbox engine, no other outbounds/direct fallback.
    return {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "tun", "tag": "twinconnect-tun",
            "address": ["172.19.0.1/30"],
            "auto_route": True, "auto_redirect": False,
            "strict_route": False, "stack": "system",
        }],
        "outbounds": [out],
        "route": {"final": "proxy", "auto_detect_interface": True},
    }


def validate_mbox_tun_config(value: dict) -> None:
    """Defense in depth in the ROOT daemon: reject arbitrary Mieru configs."""
    if not isinstance(value, dict) or set(value) != {
            "log", "inbounds", "outbounds", "route"}:
        raise ValueError("MIERU_TUN_SCHEMA_INVALID")
    if not isinstance(value["outbounds"], list) or len(value["outbounds"]) != 1:
        raise ValueError("MIERU_TUN_OUTBOUNDS_INVALID")
    outbound = value["outbounds"][0]
    if not isinstance(outbound, dict) or set(outbound) != {
            "type", "tag", "server", "server_port", "transport",
            "username", "password"}:
        raise ValueError("MIERU_TUN_OUTBOUND_INVALID")
    if outbound["type"] != "mieru" or outbound["tag"] != "proxy":
        raise ValueError("MIERU_TUN_OUTBOUND_INVALID")
    try:
        if not ipaddress.IPv4Address(outbound["server"]).is_global:
            raise ValueError
    except (ValueError, ipaddress.AddressValueError, TypeError):
        raise ValueError("MIERU_TUN_ENDPOINT_INVALID") from None
    if type(outbound["server_port"]) is not int or not 1 <= outbound["server_port"] <= 65535:
        raise ValueError("MIERU_TUN_PORT_INVALID")
    if outbound["transport"] != "TCP":
        raise ValueError("MIERU_TUN_TRANSPORT_INVALID")
    if not isinstance(outbound["username"], str) or (
            not 1 <= len(outbound["username"].encode("utf-8")) <= 64):
        raise ValueError("MIERU_TUN_USER_INVALID")
    if not isinstance(outbound["password"], str) or (
            not 1 <= len(outbound["password"].encode("utf-8")) <= 64):
        raise ValueError("MIERU_TUN_PASSWORD_INVALID")
    inbound = value["inbounds"]
    if (not isinstance(inbound, list) or len(inbound) != 1 or
            not isinstance(inbound[0], dict) or
            set(inbound[0]) != {"type", "tag", "address", "auto_route",
                                "auto_redirect", "strict_route", "stack"} or
            inbound[0] != {
                "type": "tun", "tag": "twinconnect-tun",
                "address": ["172.19.0.1/30"], "auto_route": True,
                "auto_redirect": False, "strict_route": False,
                "stack": "system"}):
        raise ValueError("MIERU_TUN_INBOUND_INVALID")
    if value["route"] != {"final": "proxy", "auto_detect_interface": True}:
        # The root-only management guard will later append exact /32
        # exclusions to the validated inbound. They are NOT user supplied.
        raise ValueError("MIERU_TUN_ROUTE_INVALID")
    # No filesystem side effect: call the shared full-TUN route validator
    # only in the root daemon after writing the private 0600 config file.


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
    candidate = len(sys.argv) == 2 and sys.argv[1] == "--candidate"
    if len(sys.argv) > 1 and not candidate:
        print(json.dumps({"state": "rejected", "reason": "MIERU_INVALID_ACTION"}))
        return 2
    try:
        data = sys.stdin.buffer.read(MAX_CONFIG_BYTES + 1)
        if len(data) > MAX_CONFIG_BYTES:
            raise ValueError("MIERU_CONFIG_TOO_LARGE")
        profile = json.loads(data)
        summary = prepare_mbox_tun(profile) if candidate else safe_preflight_summary(profile)
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