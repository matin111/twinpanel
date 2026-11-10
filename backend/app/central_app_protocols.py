"""Shared VPN client protocol definitions.

Aliases and canonical IDs are aligned with the actual panel Connection page.
Engine families describe *planned* native integration, not runtime support.
This file must remain credential-free, deterministic and safe to import in
tests; no SSH, provisioning, or network probe is performed here.
"""
from __future__ import annotations

from dataclasses import dataclass

from .routers.public_connection_modern_delivery_v13 import CANONICAL_PROTOCOLS


@dataclass(frozen=True)
class ProtocolContract:
    code: str
    title: str
    family: str
    profile_format: str
    note: str = ""


# Profiles are not interchangeable: e.g. AmneziaWG is not ordinary WireGuard,
# and ShadowTLS may need a Shadowsocks->ShadowTLS chain (never flatten it).
# Xray VLESS XHTTP cannot be assumed supported by a generic sing-box engine.
_PROTOCOLS: tuple[ProtocolContract, ...] = (
    ProtocolContract("cisco", "Cisco / OpenConnect", "openconnect", "username_password"),
    ProtocolContract("openvpn", "OpenVPN", "openvpn", "ovpn"),
    ProtocolContract("wireguard", "WireGuard", "wireguard", "wg_conf"),
    ProtocolContract("l2tp", "L2TP / IPsec", "native_l2tp", "username_password_psk",
                     "OS-native L2TP varies by platform; do not assume iOS support."),
    ProtocolContract("v2ray", "V2Ray / Xray", "xray", "xray_profiles",
                     "Preserve TCP TLS, XHTTP Reality and WS TLS individually."),
    ProtocolContract("hysteria2", "Hysteria2", "singbox", "singbox_or_uri"),
    ProtocolContract("tuic", "TUIC", "singbox", "singbox_or_uri"),
    ProtocolContract("anytls", "AnyTLS", "singbox", "singbox_or_uri"),
    ProtocolContract("naive", "NaiveProxy", "singbox", "singbox_or_uri",
                     "Requires a sing-box build with Naive outbound support."),
    ProtocolContract("shadowtls", "ShadowTLS", "singbox", "singbox_chain",
                     "Retain Shadowsocks detour and ShadowTLS outbounds."),
    ProtocolContract("snell", "Snell", "singbox", "singbox_or_uri"),
    ProtocolContract("socks5", "SOCKS5", "singbox", "singbox_or_uri",
                     "SOCKS5 alone does not encrypt traffic."),
    ProtocolContract("mieru", "Mieru", "mieru", "mieru_profile"),
    ProtocolContract("trusttunnel", "TrustTunnel", "trusttunnel", "trusttunnel_profile"),
    ProtocolContract("amneziawg", "AmneziaWG", "amneziawg", "awg_conf"),
    ProtocolContract("sudoku", "Sudoku", "sudoku", "sudoku_profile"),
)

PROTOCOL_CONTRACTS = {item.code: item for item in _PROTOCOLS}
assert len(PROTOCOL_CONTRACTS) == 16
assert set(PROTOCOL_CONTRACTS) == set(CANONICAL_PROTOCOLS)


def normalize_protocol(value: str) -> str:
    code = str(value or "").strip().lower()
    code = {
        "xray": "v2ray",
        "vless": "v2ray",
        "openconnect": "cisco",
        "anyconnect": "cisco",
        "l2tp/ipsec": "l2tp",
        "naiveproxy": "naive",
        "hy2": "hysteria2",
        "socks": "socks5",
        "awg": "amneziawg",
    }.get(code, code)
    return code if code in PROTOCOL_CONTRACTS else ""


def protocol_catalog(selected: set[str], configured: set[str]) -> list[dict]:
    """Expose selection + stored configuration, never real-time connectivity."""
    return [
        {
            "code": definition.code,
            "title": definition.title,
            "engine_family": definition.family,
            "profile_format": definition.profile_format,
            "selected": definition.code in selected,
            "config_record_present": (
                definition.code in selected and definition.code in configured
            ),
            # Always false until a signed native client confirms the engine.
            "client_engine_ready": False,
            "note": definition.note,
        }
        for definition in _PROTOCOLS
    ]


__all__ = ["PROTOCOL_CONTRACTS", "ProtocolContract", "protocol_catalog", "normalize_protocol"]
