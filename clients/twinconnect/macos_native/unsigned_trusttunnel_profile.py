#!/usr/bin/env python3
"""Review subscribed TrustTunnel tt:// endpoints for unsigned macOS SOCKS.

Only the official TrustTunnel CLI (as an unprivileged local SOCKS listener)
is authorized to consume the resulting TOML. This does NOT start a system VPN
or change routes/DNS, and it never authorizes 'skip_verification'.
"""
from __future__ import annotations

import base64
import ipaddress
import json
import re
import ssl
import sys

MAX_LINK_BYTES = 16384
SOCKS_PORT = 17121
MAX_CERT_BYTES = 8192
_HOST = re.compile(r"(?=.{4,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}\Z")


class ProfileRejected(ValueError):
    pass


def fail(code: str):
    raise ProfileRejected(code)


def varint(raw: bytes, offset: int) -> tuple[int, int]:
    if offset >= len(raw):
        fail("TRUSTTUNNEL_TLV_TRUNCATED")
    count = 1 << (raw[offset] >> 6)
    if offset + count > len(raw):
        fail("TRUSTTUNNEL_TLV_TRUNCATED")
    number = raw[offset] & 0x3F
    for i in range(1, count):
        number = (number << 8) | raw[offset + i]
    return number, offset + count


def utf8_value(raw: bytes, tag: int, max_len=255) -> str:
    if not raw or len(raw) > max_len:
        fail("TRUSTTUNNEL_FIELD_LENGTH_INVALID")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError:
        fail("TRUSTTUNNEL_FIELD_ENCODING_INVALID")
    if any(ord(c) < 32 or ord(c) == 127 for c in text):
        fail("TRUSTTUNNEL_CONTROL_CHAR_REJECTED")
    return text


def host_valid(host: str) -> bool:
    if not isinstance(host, str):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return bool(_HOST.fullmatch(host))


def public_endpoint(raw: str) -> str:
    value = utf8_value(raw.encode("utf-8"), 2, 330)
    # IPv6 addresses use brackets. For now only IPv4 and public DNS are
    # allowed: the desktop root TUN handles IPv4-only endpoints separately.
    if value.count(":") != 1:
        fail("TRUSTTUNNEL_ENDPOINT_INVALID")
    host, port_text = value.rsplit(":", 1)
    if not host_valid(host) or not port_text.isdecimal():
        fail("TRUSTTUNNEL_ENDPOINT_INVALID")
    port = int(port_text)
    if not 1 <= port <= 65535:
        fail("TRUSTTUNNEL_PORT_INVALID")
    return f"{host}:{port}"


def der_chain_to_pem(raw: bytes) -> str:
    if not raw or len(raw) > MAX_CERT_BYTES:
        fail("TRUSTTUNNEL_CERTIFICATE_REQUIRED")
    certs = []
    pos = 0
    while pos < len(raw):
        if len(certs) >= 4 or raw[pos] != 0x30 or pos + 2 > len(raw):
            fail("TRUSTTUNNEL_CERTIFICATE_INVALID")
        length_octet = raw[pos + 1]
        if length_octet < 128:
            size, prefix = length_octet, 2
        else:
            nbytes = length_octet & 0x7f
            if not 1 <= nbytes <= 3 or pos + 2 + nbytes > len(raw):
                fail("TRUSTTUNNEL_CERTIFICATE_INVALID")
            size = int.from_bytes(raw[pos + 2:pos + 2 + nbytes], "big")
            prefix = nbytes + 2
        end = pos + prefix + size
        if size < 128 or end > len(raw):
            fail("TRUSTTUNNEL_CERTIFICATE_INVALID")
        certs.append(ssl.DER_cert_to_PEM_cert(raw[pos:end]))
        pos = end
    return "".join(certs)


def decode_deeplink(link: str) -> dict:
    if not isinstance(link, str) or not link.startswith("tt://?") or (
            not 12 <= len(link) <= MAX_LINK_BYTES):
        fail("TRUSTTUNNEL_DEEPLINK_INVALID")
    payload = link[6:]
    if re.fullmatch(r"[a-zA-Z0-9_-]+", payload) is None:
        fail("TRUSTTUNNEL_DEEPLINK_INVALID")
    try:
        data = base64.b64decode(
            payload + "=" * ((-len(payload)) % 4), altchars=b"-_", validate=True)
    except (ValueError, base64.binascii.Error):
        fail("TRUSTTUNNEL_DEEPLINK_INVALID")
    if not data or len(data) > MAX_LINK_BYTES:
        fail("TRUSTTUNNEL_DEEPLINK_INVALID")
    fields: dict[int, list[bytes]] = {}
    pos = 0
    while pos < len(data):
        tag, pos = varint(data, pos)
        size, pos = varint(data, pos)
        if size > MAX_LINK_BYTES or pos + size > len(data):
            fail("TRUSTTUNNEL_TLV_TRUNCATED")
        if tag > 16:
            fail("TRUSTTUNNEL_FIELD_UNSUPPORTED")
        fields.setdefault(tag, []).append(data[pos:pos + size])
        pos += size
    # Unknown/new fields fail closed rather than silently alter authentication
    # or certificate settings until the bundled CLI version is reviewed.
    supported = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13}
    if set(fields) - supported:
        fail("TRUSTTUNNEL_FIELD_UNSUPPORTED")
    for tag, values in fields.items():
        if tag != 2 and len(values) != 1:
            fail("TRUSTTUNNEL_DUPLICATE_FIELD")
    for tag in (1, 2, 5, 6, 8):
        if tag not in fields:
            fail("TRUSTTUNNEL_REQUIRED_FIELD_MISSING")
    version = varint(fields[0][0], 0)[0] if 0 in fields else 0
    if version > 1:
        fail("TRUSTTUNNEL_VERSION_UNSUPPORTED")
    if 4 in fields and fields[4][0] not in (b"\x00", b"\x01"):
        fail("TRUSTTUNNEL_IPV6_FLAG_INVALID")
    if 7 in fields and fields[7][0] != b"\x00":
        fail("TRUSTTUNNEL_INSECURE_TLS_REJECTED")
    if 3 in fields:
        fail("TRUSTTUNNEL_CUSTOM_SNI_UNREVIEWED")
    if 11 in fields:
        fail("TRUSTTUNNEL_CLIENT_RANDOM_UNREVIEWED")
    if 10 in fields and fields[10][0] != b"\x00":
        fail("TRUSTTUNNEL_ANTIDPI_UNREVIEWED")
    if 9 in fields and fields[9][0] != b"\x01":
        fail("TRUSTTUNNEL_ONLY_HTTP2_REVIEWED")
    hostname = utf8_value(fields[1][0], 1)
    if not host_valid(hostname):
        fail("TRUSTTUNNEL_HOSTNAME_INVALID")
    addresses = [public_endpoint(raw.decode("utf-8")) for raw in fields[2]]
    if not 1 <= len(addresses) <= 8:
        fail("TRUSTTUNNEL_ENDPOINT_INVALID")
    username = utf8_value(fields[5][0], 5, 128)
    password = utf8_value(fields[6][0], 6, 512)
    certificate = der_chain_to_pem(fields[8][0])
    return {
        "hostname": hostname, "addresses": addresses,
        "username": username, "password": password,
        "certificate": certificate,
        "has_ipv6": fields.get(4, [b"\x01"])[0] == b"\x01",
        "upstream_protocol": "http2",
    }


def toml_for_socks(link: str, port: int = SOCKS_PORT) -> str:
    return toml_from_settings(decode_deeplink(link), port)


def trusted_unsigned_runtime(link: str) -> tuple[str, tuple[str, ...]]:
    """Pin the entitled TrustTunnel endpoint before activating system TUN.

    Use only the reviewed tt:// address, never the Exit probe IP as a
    substitute for an Iran tunnel ingress. Returns root-private TOML and
    public endpoint addresses to exclude from the system route.
    """
    from unsigned_mieru_profile import resolve_authenticated_ingress_domain

    settings = decode_deeplink(link)
    pinned = []
    ips = []
    for address in settings["addresses"]:
        name, port = address.rsplit(":", 1)
        try:
            ip = ipaddress.IPv4Address(name)
            if not ip.is_global:
                fail("TRUSTTUNNEL_ENDPOINT_PUBLIC_IPV4_REQUIRED")
            value = str(ip)
        except ipaddress.AddressValueError:
            value = resolve_authenticated_ingress_domain(name)
        pinned.append(value + ":" + port)
        ips.append(value)
    if not 1 <= len(set(ips)) <= 8:
        fail("TRUSTTUNNEL_ENDPOINT_IPV4_INVALID")
    settings["addresses"] = list(dict.fromkeys(pinned))
    return toml_from_settings(settings, SOCKS_PORT), tuple(sorted(set(ips)))


def toml_from_settings(settings: dict, port: int = SOCKS_PORT) -> str:
    """Private TOML: loopback listener only, no privileged route management."""
    if type(port) is not int or not 1024 <= port <= 65535:
        fail("TRUSTTUNNEL_SOCKS_PORT_INVALID")
    literal = lambda x: json.dumps(x, ensure_ascii=True)
    return "\n".join([
        'loglevel = "error"',
        'vpn_mode = "general"',
        'killswitch_enabled = false',
        '',
        '[endpoint]',
        'hostname = ' + literal(settings["hostname"]),
        'addresses = [' + ','.join(literal(x) for x in settings["addresses"]) + ']',
        'has_ipv6 = ' + ('true' if settings["has_ipv6"] else 'false'),
        'username = ' + literal(settings["username"]),
        'password = ' + literal(settings["password"]),
        'certificate = ' + literal(settings["certificate"]),
        'skip_verification = false',
        'upstream_protocol = "http2"',
        '',
        '[listener.socks]',
        'address = ' + literal("127.0.0.1:" + str(port)),
        '',
    ])


def trusttunnel_singbox_tun() -> dict:
    """Single outbound; no arbitrary direct path or proxy settings allowed."""
    return {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "tun", "tag": "twinconnect-tun",
            "address": ["172.19.0.1/30"], "auto_route": True,
            "auto_redirect": False, "strict_route": False,
            "stack": "system",
        }],
        "outbounds": [{
            "type": "socks", "tag": "proxy",
            "server": "127.0.0.1", "server_port": SOCKS_PORT,
            "version": "5", "network": "tcp",
            # Explicit loopback overrules global auto physical-NIC binding.
            "bind_interface": "lo0",
        }],
        "route": {"final": "proxy", "auto_detect_interface": True},
    }


def main() -> int:
    try:
        data = sys.stdin.buffer.read(MAX_LINK_BYTES + 1)
        if len(data) > MAX_LINK_BYTES:
            fail("TRUSTTUNNEL_DEEPLINK_INVALID")
        link = data.decode("ascii").strip()
        if sys.argv[1:] == ["--check"]:
            item = decode_deeplink(link)
            print(json.dumps({
                "state": "profile_validated_not_connected",
                "endpoints": len(item["addresses"]),
                "certificate_verified": False,
                "socks5_started": False,
                "system_tun_started": False,
            }))
        elif sys.argv[1:] == ["--socks-toml"]:
            sys.stdout.write(toml_for_socks(link))
        else:
            fail("TRUSTTUNNEL_ACTION_INVALID")
    except (ProfileRejected, UnicodeError, ValueError) as exc:
        msg = str(exc)
        if not re.fullmatch(r"TRUSTTUNNEL_[A-Z0-9_]{3,70}", msg):
            msg = "TRUSTTUNNEL_PROFILE_INVALID"
        print(json.dumps({"state": "rejected", "reason": msg}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())