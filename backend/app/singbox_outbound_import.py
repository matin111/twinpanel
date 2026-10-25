from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit


IMPORTABLE_TYPES = {"vless", "vmess", "trojan", "shadowsocks"}


class OutboundImportError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedOutbound:
    outbound: dict[str, Any]
    source_type: str
    label: str


def _decode_b64(value: str) -> bytes:
    raw = str(value or "").strip().replace("\n", "")
    if not raw:
        raise OutboundImportError("base64 payload is empty")
    raw += "=" * ((4 - len(raw) % 4) % 4)
    try:
        return base64.urlsafe_b64decode(raw.encode("ascii"))
    except Exception as exc:
        raise OutboundImportError("invalid base64 payload") from exc


def _port(value: Any) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise OutboundImportError("server port is invalid") from exc
    if not 1 <= port <= 65535:
        raise OutboundImportError("server port must be between 1 and 65535")
    return port


def _query(parts) -> dict[str, str]:
    return {
        key: values[-1]
        for key, values in parse_qs(parts.query, keep_blank_values=True).items()
        if values
    }


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _server(parts) -> tuple[str, int]:
    host = str(parts.hostname or "").strip()
    if not host:
        raise OutboundImportError("server address is missing")
    try:
        port = parts.port
    except ValueError as exc:
        raise OutboundImportError("server port is invalid") from exc
    if port is None:
        raise OutboundImportError("server port is missing")
    return host, _port(port)


def _tls_from_query(query: dict[str, str]) -> dict[str, Any] | None:
    security = str(query.get("security") or query.get("tls") or "").strip().lower()
    if security not in {"tls", "reality"}:
        return None

    tls: dict[str, Any] = {"enabled": True}
    server_name = str(query.get("sni") or query.get("serverName") or "").strip()
    if server_name:
        tls["server_name"] = server_name

    if _truthy(query.get("allowInsecure") or query.get("insecure")):
        tls["insecure"] = True

    alpn = str(query.get("alpn") or "").strip()
    if alpn:
        tls["alpn"] = [item.strip() for item in alpn.split(",") if item.strip()]

    fingerprint = str(query.get("fp") or query.get("fingerprint") or "").strip()
    if fingerprint:
        tls["utls"] = {"enabled": True, "fingerprint": fingerprint}

    if security == "reality":
        public_key = str(query.get("pbk") or query.get("publicKey") or "").strip()
        short_id = str(query.get("sid") or query.get("shortId") or "").strip()
        if not public_key:
            raise OutboundImportError("Reality public key is missing")
        reality: dict[str, Any] = {"enabled": True, "public_key": public_key}
        if short_id:
            reality["short_id"] = short_id
        tls["reality"] = reality

    return tls


def _transport_from_query(query: dict[str, str]) -> dict[str, Any] | None:
    kind = str(query.get("type") or query.get("net") or "tcp").strip().lower()
    if kind in {"", "tcp", "raw", "none"}:
        return None

    aliases = {
        "websocket": "ws",
        "ws": "ws",
        "grpc": "grpc",
        "httpupgrade": "httpupgrade",
        "http-upgrade": "httpupgrade",
        "http": "http",
        "h2": "http",
        "quic": "quic",
    }
    mapped = aliases.get(kind)
    if not mapped:
        raise OutboundImportError(f"unsupported V2Ray transport: {kind}")

    transport: dict[str, Any] = {"type": mapped}
    path = unquote(str(query.get("path") or "").strip())
    host = str(query.get("host") or "").strip()

    if mapped in {"ws", "httpupgrade"}:
        if path:
            transport["path"] = path
        if host:
            transport["headers"] = {"Host": host}
    elif mapped == "grpc":
        service_name = unquote(
            str(query.get("serviceName") or query.get("service_name") or path or "").strip()
        )
        if service_name:
            transport["service_name"] = service_name
    elif mapped == "http":
        if path:
            transport["path"] = path
        if host:
            transport["host"] = [item.strip() for item in host.split(",") if item.strip()]

    return transport


def _label(parts, fallback: str) -> str:
    fragment = unquote(str(parts.fragment or "")).strip()
    return fragment or fallback


def _parse_vless(raw: str) -> ParsedOutbound:
    parts = urlsplit(raw)
    server, port = _server(parts)
    uuid = unquote(str(parts.username or "")).strip()
    if not uuid:
        raise OutboundImportError("VLESS UUID is missing")
    query = _query(parts)
    outbound: dict[str, Any] = {
        "type": "vless",
        "server": server,
        "server_port": port,
        "uuid": uuid,
    }
    flow = str(query.get("flow") or "").strip()
    if flow:
        outbound["flow"] = flow
    packet_encoding = str(query.get("packetEncoding") or query.get("packet_encoding") or "").strip()
    if packet_encoding:
        outbound["packet_encoding"] = packet_encoding
    tls = _tls_from_query(query)
    if tls:
        outbound["tls"] = tls
    transport = _transport_from_query(query)
    if transport:
        outbound["transport"] = transport
    return ParsedOutbound(outbound, "vless", _label(parts, f"vless-{server}"))


def _parse_trojan(raw: str) -> ParsedOutbound:
    parts = urlsplit(raw)
    server, port = _server(parts)
    password = unquote(str(parts.username or "")).strip()
    if not password:
        raise OutboundImportError("Trojan password is missing")
    query = _query(parts)
    if "security" not in query:
        query["security"] = "tls"
    outbound: dict[str, Any] = {
        "type": "trojan",
        "server": server,
        "server_port": port,
        "password": password,
    }
    tls = _tls_from_query(query)
    if tls:
        outbound["tls"] = tls
    transport = _transport_from_query(query)
    if transport:
        outbound["transport"] = transport
    return ParsedOutbound(outbound, "trojan", _label(parts, f"trojan-{server}"))


def _vmess_transport(data: dict[str, Any]) -> dict[str, Any] | None:
    query = {
        "type": str(data.get("net") or "tcp"),
        "path": str(data.get("path") or ""),
        "host": str(data.get("host") or ""),
        "serviceName": str(data.get("serviceName") or data.get("service_name") or ""),
    }
    return _transport_from_query(query)


def _parse_vmess(raw: str) -> ParsedOutbound:
    payload = raw.split("://", 1)[1].split("#", 1)[0].strip()
    try:
        data = json.loads(_decode_b64(payload).decode("utf-8"))
    except OutboundImportError:
        raise
    except Exception as exc:
        raise OutboundImportError("VMess payload is not valid JSON") from exc
    if not isinstance(data, dict):
        raise OutboundImportError("VMess payload must be an object")

    server = str(data.get("add") or data.get("server") or "").strip()
    if not server:
        raise OutboundImportError("VMess server is missing")
    uuid = str(data.get("id") or data.get("uuid") or "").strip()
    if not uuid:
        raise OutboundImportError("VMess UUID is missing")

    outbound: dict[str, Any] = {
        "type": "vmess",
        "server": server,
        "server_port": _port(data.get("port")),
        "uuid": uuid,
        "security": str(data.get("scy") or data.get("security") or "auto").strip() or "auto",
    }
    try:
        alter_id = int(data.get("aid") or data.get("alterId") or 0)
    except (TypeError, ValueError):
        alter_id = 0
    if alter_id:
        outbound["alter_id"] = alter_id

    tls_mode = str(data.get("tls") or "").strip().lower()
    if tls_mode in {"tls", "reality"}:
        query = {
            "security": tls_mode,
            "sni": str(data.get("sni") or data.get("serverName") or ""),
            "fp": str(data.get("fp") or ""),
            "allowInsecure": str(data.get("allowInsecure") or ""),
            "alpn": str(data.get("alpn") or ""),
            "pbk": str(data.get("pbk") or ""),
            "sid": str(data.get("sid") or ""),
        }
        tls = _tls_from_query(query)
        if tls:
            outbound["tls"] = tls

    transport = _vmess_transport(data)
    if transport:
        outbound["transport"] = transport
    label = str(data.get("ps") or f"vmess-{server}").strip()
    return ParsedOutbound(outbound, "vmess", label)


def _parse_ss(raw: str) -> ParsedOutbound:
    body = raw.split("://", 1)[1]
    body_no_fragment, _, fragment = body.partition("#")
    label = unquote(fragment).strip()
    main, sep, query_text = body_no_fragment.partition("?")
    plugin_query = parse_qs(query_text, keep_blank_values=True) if sep else {}

    if "@" in main:
        userinfo, endpoint = main.rsplit("@", 1)
        try:
            decoded = _decode_b64(userinfo).decode("utf-8")
        except OutboundImportError:
            decoded = unquote(userinfo)
        if ":" not in decoded:
            raise OutboundImportError("Shadowsocks method/password is invalid")
        method, password = decoded.split(":", 1)
        endpoint_parts = urlsplit("ss://x@" + endpoint)
        server, port = _server(endpoint_parts)
    else:
        decoded = _decode_b64(main).decode("utf-8")
        if "@" not in decoded:
            raise OutboundImportError("legacy Shadowsocks endpoint is invalid")
        credentials, endpoint = decoded.rsplit("@", 1)
        if ":" not in credentials:
            raise OutboundImportError("Shadowsocks method/password is invalid")
        method, password = credentials.split(":", 1)
        endpoint_parts = urlsplit("ss://x@" + endpoint)
        server, port = _server(endpoint_parts)

    method = unquote(method).strip()
    password = unquote(password).strip()
    if not method or not password:
        raise OutboundImportError("Shadowsocks method/password is missing")

    outbound: dict[str, Any] = {
        "type": "shadowsocks",
        "server": server,
        "server_port": port,
        "method": method,
        "password": password,
    }
    plugin = unquote(str((plugin_query.get("plugin") or [""])[-1])).strip()
    if plugin:
        plugin_name, _, plugin_opts = plugin.partition(";")
        outbound["plugin"] = plugin_name
        if plugin_opts:
            outbound["plugin_opts"] = plugin_opts
    return ParsedOutbound(outbound, "shadowsocks", label or f"ss-{server}")


def _sanitize_raw_outbound(item: dict[str, Any]) -> dict[str, Any]:
    kind = str(item.get("type") or "").strip().lower()
    if kind not in IMPORTABLE_TYPES:
        raise OutboundImportError(f"unsupported outbound type: {kind or 'missing'}")

    allowed_common = {"type", "server", "server_port", "tls", "transport", "multiplex", "detour"}
    allowed_by_type = {
        "vless": {"uuid", "flow", "packet_encoding"},
        "vmess": {"uuid", "security", "alter_id", "packet_encoding", "global_padding", "authenticated_length"},
        "trojan": {"password"},
        "shadowsocks": {"method", "password", "plugin", "plugin_opts", "udp_over_tcp"},
    }
    clean = {
        key: value
        for key, value in item.items()
        if key in allowed_common or key in allowed_by_type[kind]
    }
    clean["type"] = kind
    clean.pop("tag", None)
    server = str(clean.get("server") or "").strip()
    if not server:
        raise OutboundImportError("server address is missing")
    clean["server"] = server
    clean["server_port"] = _port(clean.get("server_port"))
    return clean


def _parse_json(raw: str) -> ParsedOutbound:
    try:
        data = json.loads(raw)
    except Exception as exc:
        raise OutboundImportError("config is not a supported share URI or JSON") from exc

    label = ""
    candidate: dict[str, Any] | None = None
    if isinstance(data, dict) and str(data.get("type") or "").strip().lower() in IMPORTABLE_TYPES:
        candidate = data
        label = str(data.get("tag") or "").strip()
    elif isinstance(data, dict) and isinstance(data.get("outbounds"), list):
        rows = [
            row for row in data["outbounds"]
            if isinstance(row, dict)
            and str(row.get("type") or "").strip().lower() in IMPORTABLE_TYPES
        ]
        if len(rows) != 1:
            raise OutboundImportError("JSON config must contain exactly one importable outbound")
        candidate = rows[0]
        label = str(candidate.get("tag") or "").strip()
    if candidate is None:
        raise OutboundImportError("JSON does not contain an importable outbound")

    clean = _sanitize_raw_outbound(candidate)
    kind = str(clean["type"])
    return ParsedOutbound(clean, kind, label or f"{kind}-{clean['server']}")


def parse_outbound_config(raw: str) -> ParsedOutbound:
    value = str(raw or "").strip()
    if not value:
        raise OutboundImportError("config is empty")
    lowered = value.lower()
    if lowered.startswith("vless://"):
        return _parse_vless(value)
    if lowered.startswith("vmess://"):
        return _parse_vmess(value)
    if lowered.startswith("trojan://"):
        return _parse_trojan(value)
    if lowered.startswith("ss://"):
        return _parse_ss(value)
    return _parse_json(value)


__all__ = [
    "IMPORTABLE_TYPES",
    "OutboundImportError",
    "ParsedOutbound",
    "parse_outbound_config",
]
