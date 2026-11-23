#!/usr/bin/env python3
"""Offline Hysteria2 sing-box TUN candidate for guarded *external* routing.

No Apple signing needed for the sing-box userspace engine. This module NEVER
starts an engine, changes DNS, adds routes, or reports a connected VPN.
A privileged, independent route watchdog and validated system egress are
mandatory before any eventual deployment as a system VPN.
"""
from __future__ import annotations

import ipaddress
import json
import re

MAX_BYTES = 131072
TUN_NET = "172.31.240.1/30"


def convert(profile: bytes, *, physical_interface: str) -> bytes:
    if not isinstance(profile, bytes) or not 10 <= len(profile) <= MAX_BYTES:
        raise ValueError("HY2_CONFIG_SIZE_INVALID")
    if not re.fullmatch(r"en[0-9]{1,3}", physical_interface):
        raise ValueError("HY2_PHYSICAL_INTERFACE_INVALID")
    try:
        source = json.loads(profile)
    except (UnicodeError, ValueError):
        raise ValueError("HY2_CONFIG_NOT_JSON") from None
    if not isinstance(source, dict) or set(source) - {"log", "inbounds", "outbounds", "route"}:
        raise ValueError("HY2_CONFIG_KEYS_UNTRUSTED")
    inbounds = source.get("inbounds")
    if not isinstance(inbounds, list) or len(inbounds) != 1:
        raise ValueError("HY2_SINGLE_SOCKS_INPUT_REQUIRED")
    inp = inbounds[0]
    if (not isinstance(inp, dict) or inp.get("type") not in {"mixed", "socks"} or
            inp.get("listen") != "127.0.0.1" or
            type(inp.get("listen_port")) is not int or
            not 1024 <= inp["listen_port"] <= 65535 or
            set(inp) - {"type", "tag", "listen", "listen_port"}):
        raise ValueError("HY2_REVIEWED_LOOPBACK_INPUT_REQUIRED")
    outbound = source.get("outbounds")
    if not isinstance(outbound, list) or len(outbound) != 1:
        raise ValueError("HY2_SINGLE_REMOTE_PEER_REQUIRED")
    peer = outbound[0]
    if not isinstance(peer, dict) or peer.get("type") != "hysteria2" or peer.get("tag") != "proxy":
        raise ValueError("HY2_OUTBOUND_INVALID")
    allowed = {"type", "tag", "server", "server_port", "password", "tls",
               "obfs", "up_mbps", "down_mbps"}
    if set(peer) - allowed:
        raise ValueError("HY2_UNREVIEWED_PEER_OPTIONS")
    host, port, password = peer.get("server"), peer.get("server_port"), peer.get("password")
    if not isinstance(host, str) or not re.fullmatch(r"[a-zA-Z0-9.-]{1,253}", host):
        raise ValueError("HY2_SERVER_INVALID")
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ValueError("HY2_PORT_INVALID")
    if not isinstance(password, str) or not 1 <= len(password) <= 4096:
        raise ValueError("HY2_AUTH_MISSING")
    tls = peer.get("tls")
    if (not isinstance(tls, dict) or tls.get("enabled") is not True or
            tls.get("insecure") is True or
            tls.get("disable_sni") is True or
            not isinstance(tls.get("server_name"), str) or
            not 1 <= len(tls["server_name"]) <= 253 or
            set(tls) - {"enabled", "server_name", "certificate",
                        "certificate_public_key_sha256"}):
        raise ValueError("HY2_TLS_POLICY_INVALID")
    route = source.get("route")
    if not isinstance(route, dict) or route != {"final": "proxy"}:
        raise ValueError("HY2_DIRECT_FALLBACK_FORBIDDEN")
    if "obfs" in peer:
        obfs = peer["obfs"]
        if (not isinstance(obfs, dict) or set(obfs) != {"type", "password"} or
                obfs.get("type") != "salamander" or
                not isinstance(obfs.get("password"), str) or
                not 1 <= len(obfs["password"]) <= 4096):
            raise ValueError("HY2_OBFS_INVALID")
    for rate in ("up_mbps", "down_mbps"):
        if rate in peer and (type(peer[rate]) is not int or not 1 <= peer[rate] <= 100000):
            raise ValueError("HY2_RATE_INVALID")
    # Refuse private IP destinations. The endpoint must be reached by the
    # original uplink, not by a potentially active VPN or local loopback.
    try:
        address = ipaddress.ip_address(host)
        if not address.is_global:
            raise ValueError("HY2_REMOTE_ENDPOINT_NOT_PUBLIC")
    except ValueError as exc:
        if str(exc) == "HY2_REMOTE_ENDPOINT_NOT_PUBLIC":
            raise
        # Hostnames are resolved and pinned by the future root-owned helper.
        pass
    # Inject a routing invariant under OUR control, never the panel's:
    # outbound UDP to the provider must stay on the observed physical interface.
    bound_peer = {**peer, "bind_interface": physical_interface}
    candidate = {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "tun",
            "tag": "twinconnect-hysteria2",
            "interface_name": "twinconnect-hy2",
            "address": [TUN_NET],
            "mtu": 1280,
            "auto_route": False,
            "auto_redirect": False,
            "strict_route": False,
            "stack": "system"
        }],
        "outbounds": [bound_peer],
        "route": {"final": "proxy"}
    }
    # No command/config-path fields, direct fallback, root route changes or
    # DNS policy are inherited from the panel.
    return json.dumps(candidate, separators=(",", ":"), ensure_ascii=True).encode("ascii")
