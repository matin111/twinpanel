"""Review only the entitled TwinPanel Sudoku client JSON; no arbitrary settings."""
import ipaddress
import json
import re
import socket

from unsigned_trusttunnel_profile import SOCKS_PORT, trusttunnel_singbox_tun


def reject():
    raise ValueError("SUDOKU_PROFILE_INVALID")


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            reject()
        result[key] = value
    return result


def sudoku_runtime(raw):
    if not isinstance(raw, str) or not 1 <= len(raw.encode("utf-8")) <= 16384:
        reject()
    try:
        profile = json.loads(raw, object_pairs_hook=unique)
    except (ValueError, TypeError):
        reject()
    if not isinstance(profile, dict) or profile.get("mode") != "client" or profile.get("transport") != "tcp":
        reject()
    endpoint = profile.get("server_address")
    if not isinstance(endpoint, str):
        reject()
    match = re.fullmatch(r"([A-Za-z0-9.-]{1,253}):([0-9]{1,5})", endpoint)
    if not match:
        reject()
    host, port_raw = match.groups()
    port = int(port_raw)
    key = profile.get("key")
    if not 1 <= port <= 65535 or not isinstance(key, str) or not re.fullmatch(r"(?:[0-9a-fA-F]{64}|[0-9a-fA-F]{128})", key):
        reject()
    if profile.get("aead") not in ("chacha20-poly1305", "aes-128-gcm") or profile.get("ascii") not in ("prefer_entropy", "prefer_ascii"):
        reject()
    low, high = profile.get("padding_min"), profile.get("padding_max")
    if type(low) is not int or type(high) is not int or not 0 <= low <= high <= 100:
        reject()
    if profile.get("enable_pure_downlink") is not True or profile.get("multiplex") != "off":
        reject()
    mask = profile.get("httpmask")
    if not isinstance(mask, dict) or mask.get("disable") is not False or mask.get("mode") != "auto":
        reject()
    clean_mask = {"disable": False, "mode": "auto"}
    if "tls" in mask:
        if type(mask["tls"]) is not bool:
            reject()
        clean_mask["tls"] = mask["tls"]
    for name in ("host", "path_root"):
        if name in mask:
            value = mask[name]
            if not isinstance(value, str) or not 1 <= len(value) <= 512 or any(ord(c) < 33 or ord(c) > 126 for c in value):
                reject()
            clean_mask[name] = value
    try:
        addresses = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        ips = tuple(dict.fromkeys(str(ipaddress.IPv4Address(row[4][0])) for row in addresses))
    except (OSError, ValueError, IndexError):
        raise ValueError("SUDOKU_ENDPOINT_UNRESOLVED") from None
    if not ips or not all(ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError("SUDOKU_ENDPOINT_NOT_PUBLIC")
    # Preserve delivered port, credentials, cipher and mask; never permit
    # remote routing rules, external rule downloads or non-loopback listeners.
    runtime = {"mode": "client", "transport": "tcp",
        "server_address": f"{ips[0]}:{port}", "local_address": "127.0.0.1",
        "local_port": SOCKS_PORT, "key": key, "aead": profile["aead"],
        "padding_min": low, "padding_max": high, "ascii": profile["ascii"],
        "enable_pure_downlink": True, "multiplex": "off",
        "httpmask": clean_mask, "rule_urls": ["global"]}
    return json.dumps(runtime, separators=(",", ":")), (ips[0],)


def sudoku_singbox_tun():
    return trusttunnel_singbox_tun()
