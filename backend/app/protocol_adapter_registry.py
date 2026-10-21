from __future__ import annotations

from copy import deepcopy
from typing import Any

from .protocol_catalog import PROTOCOL_CATALOG


REGISTRY_SCHEMA_VERSION = 1
CLASSIC_ADAPTER = "legacy-provision"

CLASSIC_PROTOCOL_KEYS: tuple[str, ...] = (
    "cisco",
    "openvpn",
    "wireguard",
    "l2tp",
    "v2ray",
)


def _field(
    key: str,
    label_fa: str,
    label_en: str,
    kind: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
    options: list[dict[str, str]] | None = None,
    help_fa: str = "",
    help_en: str = "",
) -> dict[str, Any]:
    return {
        "key": key,
        "label_fa": label_fa,
        "label_en": label_en,
        "type": kind,
        "min": minimum,
        "max": maximum,
        "options": options or [],
        "help_fa": help_fa,
        "help_en": help_en,
    }


def _option(value: str, fa: str, en: str) -> dict[str, str]:
    return {
        "value": value,
        "label_fa": fa,
        "label_en": en,
    }


def _capabilities(*, update_config: bool, domain_tls: bool = False) -> dict[str, bool]:
    # Classic disable/uninstall stays explicitly false until a separately
    # audited, rollback-safe runtime adapter exists.  The Studio must never
    # invent destructive support from an install/repair path.
    return {
        "install": True,
        "health": True,
        "restart": True,
        "repair": True,
        "update_config": update_config,
        "domain_tls": domain_tls,
        "disable": False,
        "uninstall": False,
    }


CLASSIC_PROTOCOL_REGISTRY: dict[str, dict[str, Any]] = {
    "cisco": {
        "key": "cisco",
        "kind": "classic",
        "title": "Cisco / OpenConnect",
        "category": "classic",
        "core": "ocserv",
        "adapter": CLASSIC_ADAPTER,
        "runtime_status": "ready",
        "transport": "tcp+udp",
        "default_port": 443,
        "port_text": "443",
        "capabilities": _capabilities(update_config=True),
        "presets": {
            "recommended": {"port": 443},
            "performance": {"port": 443},
            "compatibility": {"port": 443},
        },
        "fields": [
            _field(
                "port",
                "پورت TCP",
                "TCP port",
                "number",
                minimum=1,
                maximum=65535,
                help_fa="تنها تنظیم قابل‌اعمال فعلی Adapter کلاسیک Cisco است.",
                help_en="This is the only Cisco setting currently applied by the audited classic adapter.",
            ),
        ],
        "managed_not_editable": [
            "dtls",
            "udp_port",
            "max_clients",
            "keepalive",
            "dead_peer_detection",
            "mtu",
            "compression_policy",
            "tls_policy",
            "certificate_source",
            "session_timeout",
            "reconnect_behavior",
        ],
    },
    "openvpn": {
        "key": "openvpn",
        "kind": "classic",
        "title": "OpenVPN",
        "category": "classic",
        "core": "OpenVPN",
        "adapter": CLASSIC_ADAPTER,
        "runtime_status": "ready",
        "transport": "udp",
        "default_port": 1194,
        "port_text": "1194",
        "capabilities": _capabilities(update_config=True),
        "presets": {
            "recommended": {"port": 1194, "transport": "udp"},
            "performance": {"port": 1194, "transport": "udp"},
            "compatibility": {"port": 1194, "transport": "tcp"},
        },
        "fields": [
            _field(
                "port",
                "پورت Listener",
                "Listener port",
                "number",
                minimum=1,
                maximum=65535,
            ),
            _field(
                "transport",
                "Transport",
                "Transport",
                "select",
                options=[
                    _option("udp", "UDP (پیشنهادی)", "UDP (recommended)"),
                    _option("tcp", "TCP / سازگاری", "TCP / compatibility"),
                ],
            ),
        ],
        "managed_not_editable": [
            "cipher",
            "data_ciphers",
            "auth",
            "tls_version",
            "mtu",
            "mssfix",
            "keepalive",
            "reneg_sec",
            "topology",
            "compression",
            "central_pki",
            "certificate_mode",
        ],
    },
    "wireguard": {
        "key": "wireguard",
        "kind": "classic",
        "title": "WireGuard",
        "category": "classic",
        "core": "Kernel WG",
        "adapter": CLASSIC_ADAPTER,
        "runtime_status": "ready",
        "transport": "udp",
        "default_port": 51820,
        "port_text": "51820",
        "capabilities": _capabilities(update_config=True),
        "presets": {
            "recommended": {"port": 51820},
            "performance": {"port": 51820},
            "compatibility": {"port": 51820},
        },
        "fields": [
            _field(
                "port",
                "پورت UDP",
                "UDP port",
                "number",
                minimum=1,
                maximum=65535,
            ),
        ],
        "managed_not_editable": [
            "mtu",
            "persistent_keepalive",
            "dns",
            "allowed_ips_policy",
            "ipv4_ipv6",
            "kernel_userspace",
            "peer_management_strategy",
        ],
    },
    "l2tp": {
        "key": "l2tp",
        "kind": "classic",
        "title": "L2TP / IPsec",
        "category": "compatibility",
        "core": "strongSwan + xl2tpd",
        "adapter": CLASSIC_ADAPTER,
        "runtime_status": "ready",
        "transport": "udp/ipsec",
        "default_port": None,
        "port_text": "500/4500/1701",
        "capabilities": _capabilities(update_config=False),
        "presets": {
            "recommended": {},
            "performance": {},
            "compatibility": {},
        },
        "fields": [],
        "managed_not_editable": [
            "ports",
            "ipsec_psk",
            "encryption_proposal",
            "ike_proposal",
            "dpd",
            "nat_t",
            "address_pool",
            "dns",
            "ppp_mtu_mru",
        ],
    },
    "v2ray": {
        "key": "v2ray",
        "kind": "classic",
        "title": "V2Ray / Xray",
        "category": "classic",
        "core": "Xray",
        "adapter": CLASSIC_ADAPTER,
        "runtime_status": "ready",
        "transport": "tcp/tls/reality",
        "default_port": 8443,
        "port_text": "8443",
        "capabilities": _capabilities(update_config=True, domain_tls=True),
        "presets": {
            "recommended": {"port": 8443},
            "performance": {"port": 8443},
            "compatibility": {"port": 8443},
        },
        "fields": [
            _field(
                "port",
                "Base Port",
                "Base port",
                "number",
                minimum=1,
                maximum=65535,
                help_fa="پروفایل‌های Xray موجود از Runtime فعلی TwinPanel استفاده می‌کنند.",
                help_en="Existing Xray profiles remain owned by the current TwinPanel runtime.",
            ),
        ],
        "managed_not_editable": [
            "profiles",
            "xhttp_reality",
            "grpc_reality",
            "websocket_tls",
            "httpupgrade_tls",
            "reality",
            "sni",
            "fingerprint",
            "flow",
            "transport_specific_settings",
        ],
    },
}


def classic_definition(protocol: str) -> dict[str, Any]:
    definition = CLASSIC_PROTOCOL_REGISTRY.get(protocol)
    if definition is None:
        raise KeyError(protocol)
    return deepcopy(definition)


def classic_catalog_payload() -> list[dict[str, Any]]:
    return [classic_definition(key) for key in CLASSIC_PROTOCOL_KEYS]


def _modern_capabilities(definition: dict[str, Any]) -> dict[str, bool]:
    ready = definition.get("runtime_status") == "ready"
    return {
        "install": ready,
        "preview": True,
        "health": ready,
        "restart": False,
        "repair": ready,
        "update_config": ready,
        "domain_tls": False,
        "disable": False,
        "uninstall": ready,
    }


def unified_registry_payload() -> dict[str, Any]:
    protocols: list[dict[str, Any]] = []

    for key in CLASSIC_PROTOCOL_KEYS:
        protocols.append(classic_definition(key))

    for key, source in PROTOCOL_CATALOG.items():
        definition = deepcopy(source)
        definition.update(
            {
                "key": key,
                "kind": "modern",
                "capabilities": _modern_capabilities(source),
            }
        )
        protocols.append(definition)

    return {
        "ok": True,
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "protocols": protocols,
    }
