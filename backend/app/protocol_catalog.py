from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any


SCHEMA_VERSION = 1


def _field(
    key: str,
    label_fa: str,
    label_en: str,
    kind: str,
    *,
    help_fa: str = "",
    help_en: str = "",
    options: list[dict[str, str]] | None = None,
    minimum: int | float | None = None,
    maximum: int | float | None = None,
    advanced: bool = False,
    secret: bool = False,
) -> dict[str, Any]:
    return {
        "key": key,
        "label_fa": label_fa,
        "label_en": label_en,
        "type": kind,
        "help_fa": help_fa,
        "help_en": help_en,
        "options": options or [],
        "min": minimum,
        "max": maximum,
        "advanced": advanced,
        "secret": secret,
    }


def _option(value: str, fa: str, en: str) -> dict[str, str]:
    return {"value": value, "label_fa": fa, "label_en": en}


# One canonical source of truth for the modern protocol control plane.
# Runtime adapters may support only a subset; the catalog deliberately exposes
# adapter readiness instead of pretending an unavailable protocol is usable.
PROTOCOL_CATALOG: dict[str, dict[str, Any]] = {
    "hysteria2": {
        "title": "Hysteria2",
        "category": "recommended",
        "core": "sing-box",
        "adapter": "sing-box",
        "runtime_status": "ready",
        "transport": "udp",
        "default_port": 8444,
        "tls": True,
        "recommended_for": ["mobile", "lossy", "long_distance"],
        "formats": {"share": True, "clash": True, "sing_box": True, "xray": False},
        "platforms": ["android", "ios", "windows", "macos", "linux"],
        "presets": {
            "recommended": {
                "bbr_profile": "standard",
                "ignore_client_bandwidth": True,
                "obfs_type": "salamander",
                "up_mbps": 0,
                "down_mbps": 0,
                "masquerade": "",
            },
            "performance": {
                "bbr_profile": "aggressive",
                "ignore_client_bandwidth": True,
                "obfs_type": "none",
                "up_mbps": 0,
                "down_mbps": 0,
                "masquerade": "",
            },
            "compatibility": {
                "bbr_profile": "conservative",
                "ignore_client_bandwidth": False,
                "obfs_type": "salamander",
                "up_mbps": 100,
                "down_mbps": 100,
                "masquerade": "",
            },
        },
        "fields": [
            _field("bbr_profile", "پروفایل BBR", "BBR profile", "select", options=[
                _option("conservative", "محافظه‌کار", "Conservative"),
                _option("standard", "استاندارد (پیشنهادی)", "Standard (recommended)"),
                _option("aggressive", "تهاجمی / سرعت", "Aggressive / performance"),
            ]),
            _field("ignore_client_bandwidth", "نادیده گرفتن محدودیت پهنای‌باند کلاینت", "Ignore client bandwidth", "boolean", help_fa="برای BBR و شبکه‌های متغیر معمولاً روشن بماند."),
            _field("obfs_type", "مبهم‌سازی QUIC", "QUIC obfuscation", "select", options=[
                _option("none", "خاموش", "Off"),
                _option("salamander", "Salamander (پیشنهادی)", "Salamander (recommended)"),
                _option("gecko", "Gecko", "Gecko"),
            ]),
            _field("obfs_password", "رمز Obfuscation", "Obfuscation password", "password", advanced=True, secret=True, help_fa="اگر خالی باشد TwinPanel یک مقدار پایدار و امن تولید می‌کند."),
            _field("up_mbps", "سقف Upload سرور (Mbps)", "Server upload cap (Mbps)", "number", minimum=0, maximum=100000, advanced=True, help_fa="۰ یعنی بدون سقف؛ با ignore_client_bandwidth همزمان محدودیت صریح نگذارید."),
            _field("down_mbps", "سقف Download سرور (Mbps)", "Server download cap (Mbps)", "number", minimum=0, maximum=100000, advanced=True),
            _field("masquerade", "Masquerade URL", "Masquerade URL", "text", advanced=True, help_fa="اختیاری؛ برای ظاهر HTTP سرویس. خالی = غیرفعال."),
        ],
    },
    "tuic": {
        "title": "TUIC v5",
        "category": "recommended",
        "core": "sing-box",
        "adapter": "sing-box",
        "runtime_status": "ready",
        "transport": "udp",
        "default_port": 8445,
        "tls": True,
        "recommended_for": ["mobile", "low_latency", "quic"],
        "formats": {"share": True, "clash": True, "sing_box": True, "xray": False},
        "platforms": ["android", "ios", "windows", "macos", "linux"],
        "presets": {
            "recommended": {"congestion_control": "cubic", "auth_timeout": "3s", "heartbeat": "10s", "zero_rtt_handshake": False},
            "performance": {"congestion_control": "bbr", "auth_timeout": "3s", "heartbeat": "10s", "zero_rtt_handshake": False},
            "compatibility": {"congestion_control": "cubic", "auth_timeout": "5s", "heartbeat": "15s", "zero_rtt_handshake": False},
        },
        "fields": [
            _field("congestion_control", "کنترل ازدحام", "Congestion control", "select", options=[
                _option("cubic", "CUBIC (پیشنهادی)", "CUBIC (recommended)"),
                _option("bbr", "BBR", "BBR"),
                _option("new_reno", "New Reno", "New Reno"),
            ]),
            _field("auth_timeout", "مهلت احراز هویت", "Authentication timeout", "duration", advanced=True, help_fa="مقدار پیش‌فرض امن sing-box برابر 3s است."),
            _field("heartbeat", "Heartbeat", "Heartbeat", "duration", advanced=True, help_fa="پیشنهادی 10s."),
            _field("zero_rtt_handshake", "QUIC 0-RTT", "QUIC 0-RTT", "boolean", advanced=True, help_fa="به دلیل Replay Attack خاموش نگه دارید."),
        ],
    },
    "anytls": {
        "title": "AnyTLS",
        "category": "recommended",
        "core": "sing-box",
        "adapter": "sing-box",
        "runtime_status": "ready",
        "transport": "tcp",
        "default_port": 8446,
        "tls": True,
        "recommended_for": ["tcp", "compatibility", "restricted_network"],
        "formats": {"share": True, "clash": True, "sing_box": True, "xray": False},
        "platforms": ["android", "ios", "windows", "macos", "linux"],
        "presets": {
            "recommended": {"padding_scheme": "default"},
            "performance": {"padding_scheme": "default"},
            "compatibility": {"padding_scheme": "default"},
        },
        "fields": [
            _field("padding_scheme", "Padding Scheme", "Padding scheme", "select", options=[
                _option("default", "پیش‌فرض رسمی (پیشنهادی)", "Official default (recommended)"),
                _option("custom", "سفارشی", "Custom"),
            ]),
            _field("padding_scheme_custom", "Padding سفارشی", "Custom padding lines", "textarea", advanced=True, help_fa="هر خط یک Rule. فقط وقتی Custom انتخاب شده استفاده می‌شود."),
        ],
    },
    "naive": {
        "title": "NaiveProxy",
        "category": "camouflage",
        "core": "sing-box",
        "adapter": "sing-box",
        "runtime_status": "ready",
        "transport": "tcp",
        "default_port": 8447,
        "tls": True,
        "recommended_for": ["browser_like", "tls", "restricted_network"],
        "formats": {"share": True, "clash": False, "sing_box": True, "xray": False},
        "platforms": ["android", "ios", "windows", "macos", "linux"],
        "warnings": ["trusted_tls_recommended"],
        "presets": {
            "recommended": {"network": "tcp", "quic_congestion_control": "bbr", "tls_mode": "managed"},
            "performance": {"network": "udp", "quic_congestion_control": "bbr", "tls_mode": "managed"},
            "compatibility": {"network": "tcp", "quic_congestion_control": "cubic", "tls_mode": "managed"},
        },
        "fields": [
            _field("network", "شبکه", "Network", "select", options=[
                _option("tcp", "TCP / HTTP2 (پیشنهادی)", "TCP / HTTP2 (recommended)"),
                _option("udp", "UDP / QUIC", "UDP / QUIC"),
                _option("both", "TCP + UDP", "TCP + UDP"),
            ]),
            _field("quic_congestion_control", "کنترل ازدحام QUIC", "QUIC congestion control", "select", advanced=True, options=[
                _option("bbr", "BBR (پیشنهادی سرور)", "BBR (server recommended)"),
                _option("cubic", "CUBIC", "CUBIC"),
                _option("reno", "Reno", "Reno"),
            ]),
            _field("tls_mode", "گواهی TLS", "TLS certificate", "select", options=[
                _option("managed", "گواهی مدیریت‌شده TwinPanel", "TwinPanel managed certificate"),
                _option("custom", "مسیر گواهی معتبر", "Custom trusted certificate paths"),
            ]),
            _field("certificate_path", "مسیر Fullchain", "Fullchain path", "text", advanced=True),
            _field("key_path", "مسیر Private Key", "Private key path", "text", advanced=True, secret=True),
        ],
    },
    "shadowtls": {
        "title": "ShadowTLS v3",
        "category": "camouflage",
        "core": "sing-box",
        "adapter": "sing-box",
        "runtime_status": "ready",
        "transport": "tcp",
        "default_port": 8448,
        "tls": False,
        "recommended_for": ["tls_camouflage", "tcp", "restricted_network"],
        "formats": {"share": False, "clash": False, "sing_box": True, "xray": False},
        "platforms": ["android", "ios", "windows", "macos", "linux"],
        "presets": {
            "recommended": {"version": 3, "handshake_server": "www.microsoft.com", "handshake_port": 443, "strict_mode": True, "wildcard_sni": "off"},
            "performance": {"version": 3, "handshake_server": "www.microsoft.com", "handshake_port": 443, "strict_mode": True, "wildcard_sni": "authed"},
            "compatibility": {"version": 3, "handshake_server": "www.microsoft.com", "handshake_port": 443, "strict_mode": False, "wildcard_sni": "off"},
        },
        "fields": [
            _field("version", "نسخه", "Version", "select", options=[_option("3", "v3 (پیشنهادی)", "v3 (recommended)")]),
            _field("handshake_server", "TLS Handshake Host", "TLS handshake host", "text", help_fa="یک مقصد پایدار با TLS 1.3 انتخاب کنید."),
            _field("handshake_port", "Handshake Port", "Handshake port", "number", minimum=1, maximum=65535),
            _field("strict_mode", "Strict Mode", "Strict mode", "boolean", help_fa="برای v3 پیشنهاد می‌شود."),
            _field("wildcard_sni", "Wildcard SNI", "Wildcard SNI", "select", advanced=True, options=[
                _option("off", "خاموش (پیشنهادی)", "Off (recommended)"),
                _option("authed", "فقط احراز‌شده", "Authenticated only"),
                _option("all", "همه", "All"),
            ]),
        ],
    },
    "snell": {
        "title": "Snell",
        "category": "camouflage",
        "core": "sing-box",
        "adapter": "sing-box",
        "runtime_status": "ready",
        "transport": "tcp",
        "default_port": 8449,
        "tls": False,
        "recommended_for": ["tcp", "traffic_shaping", "advanced"],
        "formats": {"share": False, "clash": False, "sing_box": True, "xray": False},
        "platforms": ["ios", "macos", "android", "windows", "linux"],
        "presets": {
            "recommended": {"version": 6, "mode": "default", "obfs_mode": "none"},
            "performance": {"version": 6, "mode": "unshaped", "obfs_mode": "none"},
            "compatibility": {"version": 5, "mode": "default", "obfs_mode": "http"},
        },
        "fields": [
            _field("version", "نسخه Snell", "Snell version", "select", options=[
                _option("6", "v6 (پیشنهادی)", "v6 (recommended)"),
                _option("5", "v5 / سازگاری", "v5 / compatibility"),
            ]),
            _field("mode", "Traffic Shaping v6", "v6 traffic shaping", "select", options=[
                _option("default", "Default (پیشنهادی)", "Default (recommended)"),
                _option("unshaped", "Unshaped", "Unshaped"),
                _option("unsafe-raw", "Unsafe Raw", "Unsafe raw"),
            ]),
            _field("obfs_mode", "HTTP Obfs v5", "v5 HTTP obfuscation", "select", advanced=True, options=[
                _option("none", "خاموش", "Off"),
                _option("http", "HTTP", "HTTP"),
            ]),
            _field("psk", "PSK سرور", "Server PSK", "password", advanced=True, secret=True, help_fa="اگر خالی باشد TwinPanel مقدار امن پایدار تولید می‌کند. برای v6 حداقل ۱۲ بایت."),
        ],
    },
    "mieru": {
        "title": "Mieru",
        "category": "standalone",
        "core": "mita",
        "adapter": "mieru",
        "runtime_status": "adapter_pending",
        "transport": "tcp_udp",
        "default_port": 8450,
        "tls": False,
        "recommended_for": ["mobile", "tcp_udp", "per_user_metrics"],
        "formats": {"share": True, "clash": True, "sing_box": False, "xray": False},
        "platforms": ["android", "windows", "macos", "linux"],
        "presets": {
            "recommended": {"mtu": 1400, "multiplexing_level": "LOW", "handshake_mode": "STANDARD", "dual_stack": "PREFER_IPv4"},
            "performance": {"mtu": 1400, "multiplexing_level": "MIDDLE", "handshake_mode": "STANDARD", "dual_stack": "PREFER_IPv4"},
            "compatibility": {"mtu": 1280, "multiplexing_level": "LOW", "handshake_mode": "STANDARD", "dual_stack": "PREFER_IPv4"},
        },
        "fields": [
            _field("mtu", "MTU", "MTU", "number", minimum=1280, maximum=1500),
            _field("multiplexing_level", "سطح Multiplex", "Multiplexing level", "select", options=[_option("LOW", "Low (پیشنهادی)", "Low (recommended)"), _option("MIDDLE", "Middle", "Middle"), _option("HIGH", "High", "High")]),
            _field("handshake_mode", "Handshake", "Handshake mode", "select", options=[_option("STANDARD", "Standard (پیشنهادی)", "Standard (recommended)"), _option("NO_WAIT", "No Wait / 0-RTT", "No Wait / 0-RTT")]),
            _field("dual_stack", "DNS Dual Stack", "DNS dual stack", "select", advanced=True, options=[_option("PREFER_IPv4", "IPv4 ترجیحی", "Prefer IPv4"), _option("PREFER_IPv6", "IPv6 ترجیحی", "Prefer IPv6")]),
        ],
    },
    "trusttunnel": {
        "title": "TrustTunnel",
        "category": "standalone",
        "core": "trusttunnel",
        "adapter": "trusttunnel",
        "runtime_status": "adapter_pending",
        "transport": "tcp_udp_quic",
        "default_port": 8451,
        "tls": True,
        "recommended_for": ["standard_clients", "metrics", "multi_transport"],
        "formats": {"share": True, "clash": False, "sing_box": False, "xray": False},
        "platforms": ["android", "ios", "windows", "macos", "linux"],
        "presets": {
            "recommended": {"http1": True, "http2": True, "quic": True, "per_client_metrics": True, "connection_limit": 4},
            "performance": {"http1": False, "http2": True, "quic": True, "per_client_metrics": True, "connection_limit": 8},
            "compatibility": {"http1": True, "http2": True, "quic": False, "per_client_metrics": True, "connection_limit": 4},
        },
        "fields": [
            _field("http1", "HTTP/1.1", "HTTP/1.1", "boolean"),
            _field("http2", "HTTP/2", "HTTP/2", "boolean"),
            _field("quic", "QUIC", "QUIC", "boolean"),
            _field("per_client_metrics", "متریک جدا برای هر کاربر", "Per-client metrics", "boolean", help_fa="برای Quota و Session TwinPanel روشن بماند."),
            _field("connection_limit", "حد اتصال هر کاربر", "Per-user connection limit", "number", minimum=1, maximum=128),
        ],
    },
    "amneziawg": {
        "title": "AmneziaWG",
        "category": "standalone",
        "core": "amneziawg",
        "adapter": "amneziawg",
        "runtime_status": "adapter_pending",
        "transport": "udp",
        "default_port": 8452,
        "tls": False,
        "recommended_for": ["vpn", "mobile", "wireguard_compatible"],
        "formats": {"share": False, "clash": True, "sing_box": True, "xray": True},
        "platforms": ["android", "ios", "windows", "macos", "linux"],
        "presets": {
            "recommended": {"mtu": 1280, "jc": 6, "jmin": 8, "jmax": 80, "s1": 64, "s2": 96, "h1": 101, "h2": 202, "h3": 303, "h4": 404},
            "performance": {"mtu": 1380, "jc": 4, "jmin": 8, "jmax": 48, "s1": 32, "s2": 64, "h1": 111, "h2": 222, "h3": 333, "h4": 444},
            "compatibility": {"mtu": 1280, "jc": 8, "jmin": 8, "jmax": 80, "s1": 96, "s2": 128, "h1": 121, "h2": 242, "h3": 363, "h4": 484},
        },
        "fields": [
            _field("mtu", "MTU", "MTU", "number", minimum=1280, maximum=1500),
            _field("jc", "Jc", "Jc", "number", minimum=0, maximum=128, help_fa="بازه پیشنهادی 4 تا 12."),
            _field("jmin", "Jmin", "Jmin", "number", minimum=0, maximum=1000),
            _field("jmax", "Jmax", "Jmax", "number", minimum=0, maximum=1000),
            _field("s1", "S1", "S1", "number", minimum=0, maximum=1552, advanced=True),
            _field("s2", "S2", "S2", "number", minimum=0, maximum=1608, advanced=True),
            _field("h1", "H1", "H1", "number", minimum=1, maximum=2147483647, advanced=True),
            _field("h2", "H2", "H2", "number", minimum=1, maximum=2147483647, advanced=True),
            _field("h3", "H3", "H3", "number", minimum=1, maximum=2147483647, advanced=True),
            _field("h4", "H4", "H4", "number", minimum=1, maximum=2147483647, advanced=True),
        ],
    },
    "sudoku": {
        "title": "Sudoku",
        "category": "experimental",
        "core": "standalone",
        "adapter": "sudoku",
        "runtime_status": "experimental_pending",
        "transport": "unknown",
        "default_port": 8453,
        "tls": False,
        "recommended_for": ["experimental"],
        "formats": {"share": False, "clash": False, "sing_box": False, "xray": False},
        "platforms": [],
        "warnings": ["security_audit_required", "client_ecosystem_limited"],
        "presets": {"recommended": {}, "performance": {}, "compatibility": {}},
        "fields": [],
    },
}


PRESET_NAMES = {"recommended", "performance", "compatibility", "custom"}


def catalog_payload() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key, value in PROTOCOL_CATALOG.items():
        item = deepcopy(value)
        item["key"] = key
        item["schema_version"] = SCHEMA_VERSION
        item["installable"] = item.get("runtime_status") == "ready"
        out.append(item)
    return out


def protocol_definition(protocol: str) -> dict[str, Any]:
    key = str(protocol or "").strip().lower()
    if key not in PROTOCOL_CATALOG:
        raise ValueError(f"unsupported protocol: {key or protocol}")
    return PROTOCOL_CATALOG[key]


def _coerce(field: dict[str, Any], value: Any) -> Any:
    kind = field["type"]
    if kind == "boolean":
        if isinstance(value, bool):
            return value
        if str(value).strip().lower() in {"1", "true", "yes", "on"}:
            return True
        if str(value).strip().lower() in {"0", "false", "no", "off"}:
            return False
        raise ValueError(f"{field['key']} must be boolean")
    if kind == "number":
        if isinstance(value, bool):
            raise ValueError(f"{field['key']} must be numeric")
        number = float(value)
        if number.is_integer():
            number = int(number)
        if field.get("min") is not None and number < field["min"]:
            raise ValueError(f"{field['key']} is below minimum")
        if field.get("max") is not None and number > field["max"]:
            raise ValueError(f"{field['key']} is above maximum")
        return number
    if kind == "select":
        text = str(value)
        allowed = {str(option["value"]) for option in field.get("options", [])}
        if allowed and text not in allowed:
            # Numeric-looking select values are normalized for JSON input.
            if str(value) not in allowed:
                raise ValueError(f"invalid {field['key']}")
        return text
    if kind in {"text", "textarea", "password", "duration"}:
        return str(value or "").strip()
    return value


def resolve_settings(
    protocol: str,
    preset: str | None,
    overrides: dict[str, Any] | None,
) -> tuple[str, dict[str, Any], list[str]]:
    definition = protocol_definition(protocol)
    preset_name = str(preset or "recommended").strip().lower()
    if preset_name not in PRESET_NAMES:
        raise ValueError("invalid preset")

    base_name = "recommended" if preset_name == "custom" else preset_name
    settings = deepcopy(definition.get("presets", {}).get(base_name, {}))
    fields = {field["key"]: field for field in definition.get("fields", [])}

    for key, value in (overrides or {}).items():
        if key not in fields:
            raise ValueError(f"unknown setting for {protocol}: {key}")
        settings[key] = _coerce(fields[key], value)

    # Coerce defaults too so a future catalog typo cannot silently reach a core.
    for key in list(settings):
        if key in fields:
            settings[key] = _coerce(fields[key], settings[key])

    warnings: list[str] = list(definition.get("warnings", []))
    key = str(protocol).lower()

    if key == "tuic" and settings.get("zero_rtt_handshake"):
        warnings.append("tuic_zero_rtt_replay_risk")
    if key == "hysteria2":
        if settings.get("ignore_client_bandwidth") and (
            int(settings.get("up_mbps") or 0) > 0 or int(settings.get("down_mbps") or 0) > 0
        ):
            raise ValueError("Hysteria2 explicit bandwidth conflicts with ignore_client_bandwidth")
        if settings.get("obfs_type") in {"salamander", "gecko"} and not settings.get("obfs_password"):
            warnings.append("obfs_password_will_be_generated")
    if key == "shadowtls":
        settings["version"] = 3
        if int(settings.get("handshake_port") or 0) <= 0:
            raise ValueError("ShadowTLS handshake_port is required")
        if not str(settings.get("handshake_server") or "").strip():
            raise ValueError("ShadowTLS handshake_server is required")
    if key == "snell":
        version = int(settings.get("version") or 6)
        settings["version"] = version
        if version not in {5, 6}:
            raise ValueError("Snell version must be 5 or 6")
        if version == 6:
            settings.pop("obfs_mode", None)
        else:
            settings.pop("mode", None)
    if key == "naive" and settings.get("tls_mode") == "custom":
        if not settings.get("certificate_path") or not settings.get("key_path"):
            raise ValueError("Naive custom TLS requires certificate_path and key_path")

    return preset_name, settings, list(dict.fromkeys(warnings))


def settings_hash(protocol: str, port: int, preset: str, settings: dict[str, Any]) -> str:
    body = json.dumps(
        {
            "schema": SCHEMA_VERSION,
            "protocol": str(protocol).lower(),
            "port": int(port),
            "preset": preset,
            "settings": settings,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()
