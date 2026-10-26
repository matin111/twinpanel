from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import re
from typing import Any

from .models import (
    Node,
    NodeProtocolConfig,
    NodeType,
    Subscription,
    SubscriptionProtocol,
    SubscriptionStatus,
    Tunnel,
)
from .protocol_catalog import PROTOCOL_CATALOG
from .routers import account_delivery, tunnels
from .standalone_subscription_accounts import _sudoku_port


# TWINPANEL_MODERN_PROTOCOL_TUNNEL_BINDING_V251
#
# The legacy service plane already routes Cisco/OpenVPN/WireGuard/V2Ray and
# L2TP through the logical Iran -> Exit tunnel. Modern protocols historically
# remained direct-to-Exit because neither Desired Service Routes nor live
# subscription delivery knew about them. This additive layer extends those two
# existing abstractions without changing protocol runtimes or the legacy five.
#
# Public-port ranges intentionally follow the existing per-Exit convention:
#   legacy service ports : 20000..23999
#   Xray public profiles : 24000..27999
#   modern fixed ports   : 28000..37999 (30000 block intentionally unused)
#   Sudoku dynamic ports : 40000..49999
#
# Sudoku is different: each subscription owns a distinct listener on the Exit,
# so it cannot share one fixed target port. A deterministic collision-resolving
# allocator maps the currently desired (Exit, Subscription) pairs into the
# reserved Iran public-port pool. No credential secret is required to build the
# route because the Exit listener port is already deterministic from the
# subscription id.

FIXED_PUBLIC_PORT_BASE: dict[str, int] = {
    "hysteria2": 28000,
    "tuic": 29000,
    # 30000..30999 is deliberately left unused because Sudoku's Exit-side
    # per-user listener range starts at 30000.
    "anytls": 31000,
    "naive": 32000,
    "shadowtls": 33000,
    "snell": 34000,
    "mieru": 35000,
    "trusttunnel": 36000,
    "amneziawg": 37000,
}

MODERN_TUNNEL_PROTOCOLS = frozenset({
    *FIXED_PUBLIC_PORT_BASE,
    "sudoku",
})

SINGBOX_TUNNEL_PROTOCOLS = frozenset({
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "shadowtls",
    "snell",
})

SUDOKU_PUBLIC_PORT_START = 40000
SUDOKU_PUBLIC_PORT_END = 49999

_RUNTIME_APPLIED = False
_ORIGINAL_SERVICE_ROUTES_FOR_EXIT = None
_ORIGINAL_LIVE_CLIENT_ITEM = None


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _fixed_public_port(exit_node_id: int, protocol: str) -> int:
    protocol = str(protocol or "").strip().lower()
    if protocol not in FIXED_PUBLIC_PORT_BASE:
        raise ValueError(f"modern fixed tunnel protocol unsupported: {protocol}")

    node_id = int(exit_node_id)
    if not 1 <= node_id <= 999:
        raise RuntimeError("modern tunnel public routing supports Exit IDs 1..999")

    port = FIXED_PUBLIC_PORT_BASE[protocol] + node_id
    if not 1 <= port <= 65535:
        raise RuntimeError(f"invalid modern tunnel public port: {port}")
    return port


def _normalise_transport(protocol: str, value: Any) -> str:
    protocol = str(protocol or "").strip().lower()
    raw = str(value or "").strip().lower().replace("-", "_")

    if raw in {"tcp_udp", "tcp_udp_quic", "tcp+udp", "both"}:
        return "tcp+udp"
    if raw in {"udp", "quic"}:
        return "udp"
    if raw == "tcp":
        return "tcp"

    # Keep route generation deterministic even for old rows with blank
    # transport metadata. The catalog is the canonical fallback.
    fallback = str(
        (PROTOCOL_CATALOG.get(protocol) or {}).get("transport")
        or "tcp"
    ).strip().lower()
    if fallback in {"tcp_udp", "tcp_udp_quic", "tcp+udp", "both"}:
        return "tcp+udp"
    if fallback in {"udp", "quic"}:
        return "udp"
    return "tcp"


def _configured_modern_protocols(db, node_id: int) -> dict[str, NodeProtocolConfig]:
    rows = (
        db.query(NodeProtocolConfig)
        .filter(NodeProtocolConfig.node_id == int(node_id))
        .all()
    )
    return {
        str(row.protocol or "").strip().lower(): row
        for row in rows
        if str(row.protocol or "").strip().lower() in MODERN_TUNNEL_PROTOCOLS
    }


def _sudoku_desired_subscription_ids(db) -> list[int]:
    rows = (
        db.query(Subscription.id)
        .join(
            SubscriptionProtocol,
            SubscriptionProtocol.subscription_id == Subscription.id,
        )
        .filter(
            Subscription.status == SubscriptionStatus.ACTIVE,
            SubscriptionProtocol.protocol == "sudoku",
        )
        .order_by(Subscription.id.asc())
        .all()
    )
    return [int(row[0]) for row in rows]


def _sudoku_tunnel_exit_ids(db) -> list[int]:
    configured = (
        db.query(NodeProtocolConfig.node_id)
        .filter(NodeProtocolConfig.protocol == "sudoku")
        .distinct()
        .all()
    )

    output: list[int] = []
    for row in configured:
        node_id = int(row[0])
        node = db.get(Node, node_id)
        if (
            node is None
            or node.node_type != NodeType.EXIT
            or getattr(node, "retired_at", None) is not None
        ):
            continue

        assigned = (
            db.query(Tunnel.id)
            .filter(
                Tunnel.exit_node_id == node_id,
                Tunnel.is_active.is_(True),
            )
            .first()
        )
        if assigned is not None:
            output.append(node_id)

    return sorted(set(output))


def _sudoku_public_port_map(db) -> dict[tuple[int, int], int]:
    pairs = [
        (exit_node_id, subscription_id)
        for exit_node_id in _sudoku_tunnel_exit_ids(db)
        for subscription_id in _sudoku_desired_subscription_ids(db)
    ]

    pool_size = SUDOKU_PUBLIC_PORT_END - SUDOKU_PUBLIC_PORT_START + 1
    if len(pairs) > pool_size:
        raise RuntimeError(
            "Sudoku tunnel ingress pool exhausted; refusing colliding routes"
        )

    used: set[int] = set()
    output: dict[tuple[int, int], int] = {}

    # Hash-first allocation keeps existing endpoints stable when unrelated
    # subscriptions are added. Linear probing resolves the rare collision in a
    # deterministic order. Delivery and route reconciliation use this same
    # function, so they cannot disagree about the selected public port.
    for exit_node_id, subscription_id in sorted(pairs):
        digest = hashlib.blake2s(
            f"{exit_node_id}:{subscription_id}".encode("ascii"),
            digest_size=4,
        ).digest()
        slot = int.from_bytes(digest, "big") % pool_size

        for offset in range(pool_size):
            port = SUDOKU_PUBLIC_PORT_START + ((slot + offset) % pool_size)
            if port in used:
                continue
            used.add(port)
            output[(exit_node_id, subscription_id)] = port
            break
        else:  # pragma: no cover - guarded by the pool-size check above.
            raise RuntimeError("Sudoku tunnel ingress allocation failed")

    return output


def _sudoku_public_port(db, exit_node_id: int, subscription_id: int) -> int:
    key = (int(exit_node_id), int(subscription_id))
    mapping = _sudoku_public_port_map(db)
    if key not in mapping:
        raise RuntimeError(
            "Sudoku tunnel ingress is not desired for this Exit/subscription"
        )
    return int(mapping[key])


def _modern_routes_for_exit(db, exit_node: Node, exit_tunnel_ip: str) -> list[dict]:
    configs = _configured_modern_protocols(db, int(exit_node.id))
    output: list[dict] = []

    for protocol in FIXED_PUBLIC_PORT_BASE:
        cfg = configs.get(protocol)
        if cfg is None:
            continue

        definition = PROTOCOL_CATALOG.get(protocol) or {}
        target_port = int(cfg.port or definition.get("default_port") or 0)
        if not 1 <= target_port <= 65535:
            raise RuntimeError(
                f"invalid {protocol} target port on Exit {exit_node.id}: {target_port}"
            )

        output.append({
            "protocol": protocol,
            "exit_node_id": int(exit_node.id),
            "public_port": _fixed_public_port(int(exit_node.id), protocol),
            "target_ip": str(exit_tunnel_ip),
            "target_port": target_port,
            "transport": _normalise_transport(protocol, cfg.transport),
            "client_subnet": None,
        })

    if "sudoku" in configs:
        for subscription_id in _sudoku_desired_subscription_ids(db):
            output.append({
                "protocol": "sudoku",
                "profile": f"subscription-{subscription_id}",
                "subscription_id": int(subscription_id),
                "exit_node_id": int(exit_node.id),
                "public_port": _sudoku_public_port(
                    db,
                    int(exit_node.id),
                    int(subscription_id),
                ),
                "target_ip": str(exit_tunnel_ip),
                "target_port": int(_sudoku_port(int(subscription_id))),
                "transport": "tcp",
                "client_subnet": None,
            })

    return output


def _service_routes_for_exit_v251(db, exit_node: Node, exit_tunnel_ip: str) -> list[dict]:
    if _ORIGINAL_SERVICE_ROUTES_FOR_EXIT is None:
        raise RuntimeError("modern tunnel binding is not initialized")

    output = list(
        _ORIGINAL_SERVICE_ROUTES_FOR_EXIT(
            db,
            exit_node,
            exit_tunnel_ip,
        )
    )
    output.extend(_modern_routes_for_exit(db, exit_node, exit_tunnel_ip))
    return output


def _selected_iran_node(db, exit_node: Node) -> Node | None:
    if exit_node.node_type != NodeType.EXIT:
        return None

    rows = (
        db.query(Tunnel)
        .filter(
            Tunnel.exit_node_id == int(exit_node.id),
            Tunnel.is_active.is_(True),
        )
        .order_by(Tunnel.priority.asc(), Tunnel.id.asc())
        .all()
    )

    for tunnel in rows:
        iran = db.get(Node, int(tunnel.iran_node_id))
        if (
            iran is None
            or iran.node_type != NodeType.IRAN
            or getattr(iran, "retired_at", None) is not None
            or getattr(iran, "is_mother", False)
            or getattr(iran, "agent_url", None) == "local://core"
        ):
            continue
        return iran

    return None


def _modern_tunnel_endpoint(
    db,
    exit_node: Node,
    protocol: str,
    subscription_id: int,
) -> tuple[str, int] | None:
    protocol = str(protocol or "").strip().lower()
    if protocol not in MODERN_TUNNEL_PROTOCOLS:
        return None

    iran = _selected_iran_node(db, exit_node)
    if iran is None:
        return None

    host = str(account_delivery._node_host(iran) or "").strip()
    if not host or host in {"127.0.0.1", "localhost"}:
        raise RuntimeError(f"invalid Iran ingress for node {iran.id}")

    if protocol == "sudoku":
        port = _sudoku_public_port(
            db,
            int(exit_node.id),
            int(subscription_id),
        )
    else:
        port = _fixed_public_port(int(exit_node.id), protocol)

    return host, int(port)


def _rewrite_singbox_item(result: dict[str, Any], protocol: str, host: str, port: int) -> None:
    outbound = result.get("outbound")
    if isinstance(outbound, dict) and _enum_value(outbound.get("type")) == protocol:
        updated = dict(outbound)
        updated["server"] = host
        updated["server_port"] = int(port)
        result["outbound"] = updated

    raw = result.get("config")
    if not isinstance(raw, str) or not raw.strip():
        return

    try:
        doc = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return

    outbounds = doc.get("outbounds") if isinstance(doc, dict) else None
    if not isinstance(outbounds, list):
        return

    changed = False
    for candidate in outbounds:
        if not isinstance(candidate, dict):
            continue
        if _enum_value(candidate.get("type")) != protocol:
            continue
        candidate["server"] = host
        candidate["server_port"] = int(port)
        changed = True

    if changed:
        result["config"] = json.dumps(doc, ensure_ascii=False, indent=2)


def _rewrite_mieru_item(result: dict[str, Any], host: str, port: int) -> None:
    raw = result.get("config")
    if not isinstance(raw, str) or not raw.strip():
        return
    try:
        doc = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return

    try:
        ipaddress.ip_address(host.strip("[]"))
        ip_value, domain_value = host.strip("[]"), ""
    except ValueError:
        ip_value, domain_value = "", host

    changed = False
    for profile in doc.get("profiles", []) if isinstance(doc, dict) else []:
        if not isinstance(profile, dict):
            continue
        for server in profile.get("servers", []) if isinstance(profile.get("servers"), list) else []:
            if not isinstance(server, dict):
                continue
            server["ipAddress"] = ip_value
            server["domainName"] = domain_value
            for binding in server.get("portBindings", []) if isinstance(server.get("portBindings"), list) else []:
                if isinstance(binding, dict):
                    binding["port"] = int(port)
            changed = True

    if changed:
        result["config"] = json.dumps(doc, ensure_ascii=False, indent=2)


def _rewrite_amneziawg_item(result: dict[str, Any], host: str, port: int) -> None:
    raw = result.get("config")
    if not isinstance(raw, str) or not raw.strip():
        return
    result["config"] = re.sub(
        r"(?m)^Endpoint\s*=\s*.+$",
        f"Endpoint = {host}:{int(port)}",
        raw,
        count=1,
    )


def _quic_varint_decode(data: bytes, offset: int) -> tuple[int, int]:
    if offset >= len(data):
        raise ValueError("truncated QUIC varint")
    first = data[offset]
    length = 1 << (first >> 6)
    if offset + length > len(data):
        raise ValueError("truncated QUIC varint")
    value = first & 0x3F
    for byte in data[offset + 1 : offset + length]:
        value = (value << 8) | byte
    return value, offset + length


def _quic_varint_encode(value: int) -> bytes:
    value = int(value)
    if value < 0:
        raise ValueError("negative QUIC varint")
    for length, prefix, maximum in (
        (1, 0, 63),
        (2, 1, 16383),
        (4, 2, 1073741823),
        (8, 3, 4611686018427387903),
    ):
        if value <= maximum:
            raw = bytearray(value.to_bytes(length, "big"))
            raw[0] |= prefix << 6
            return bytes(raw)
    raise ValueError("QUIC varint too large")


def _trusttunnel_address(host: str, port: int) -> str:
    host = str(host or "").strip()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{host}:{int(port)}"


def _rewrite_trusttunnel_deeplink(value: str, host: str, port: int) -> str:
    raw = str(value or "").strip()
    if raw.startswith("tt://?"):
        prefix, payload = "tt://?", raw[6:]
    elif raw.startswith("tt://"):
        prefix, payload = "tt://", raw[5:]
    else:
        return raw

    try:
        padding = "=" * ((4 - len(payload) % 4) % 4)
        data = base64.urlsafe_b64decode(payload + padding)

        entries: list[tuple[int, bytes]] = []
        offset = 0
        while offset < len(data):
            tag, offset = _quic_varint_decode(data, offset)
            length, offset = _quic_varint_decode(data, offset)
            end = offset + int(length)
            if end > len(data):
                raise ValueError("truncated TrustTunnel TLV")
            entries.append((int(tag), data[offset:end]))
            offset = end

        address = _trusttunnel_address(host, port).encode("utf-8")
        rewritten: list[tuple[int, bytes]] = []
        address_written = False
        for tag, body in entries:
            if tag == 0x02:
                if address_written:
                    continue
                rewritten.append((tag, address))
                address_written = True
            else:
                rewritten.append((tag, body))
        if not address_written:
            rewritten.append((0x02, address))

        encoded = b"".join(
            _quic_varint_encode(tag)
            + _quic_varint_encode(len(body))
            + body
            for tag, body in rewritten
        )
        payload_out = base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")
        return prefix + payload_out
    except Exception:
        # Never corrupt an existing credential during read-time delivery. The
        # top-level server/port are still rewritten and the item remains usable
        # for clients that do not consume the deep-link field.
        return raw


def _rewrite_trusttunnel_item(result: dict[str, Any], host: str, port: int) -> None:
    for field in ("config", "uri"):
        value = result.get(field)
        if isinstance(value, str) and value.strip():
            result[field] = _rewrite_trusttunnel_deeplink(value, host, port)


def _rewrite_sudoku_item(result: dict[str, Any], host: str, port: int) -> None:
    raw = result.get("config")
    if isinstance(raw, str) and raw.strip():
        try:
            doc = json.loads(raw)
            if isinstance(doc, dict):
                doc["server_address"] = _trusttunnel_address(host, port)
                result["config"] = json.dumps(doc, ensure_ascii=False, indent=2)
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    uri = result.get("uri")
    if not isinstance(uri, str) or not uri.startswith("sudoku://"):
        return

    try:
        payload = uri[len("sudoku://") :]
        padding = "=" * ((4 - len(payload) % 4) % 4)
        doc = json.loads(base64.urlsafe_b64decode(payload + padding).decode("utf-8"))
        if not isinstance(doc, dict):
            return
        doc["h"] = host
        doc["p"] = int(port)
        encoded = base64.urlsafe_b64encode(
            json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).decode("ascii").rstrip("=")
        result["uri"] = "sudoku://" + encoded
    except Exception:
        return


def _rewrite_modern_item(
    result: dict[str, Any],
    protocol: str,
    host: str,
    port: int,
) -> dict[str, Any]:
    result["server"] = host
    result["server_ip"] = host
    result["port"] = int(port)

    if protocol in SINGBOX_TUNNEL_PROTOCOLS:
        _rewrite_singbox_item(result, protocol, host, port)
    elif protocol == "mieru":
        _rewrite_mieru_item(result, host, port)
    elif protocol == "trusttunnel":
        _rewrite_trusttunnel_item(result, host, port)
    elif protocol == "amneziawg":
        _rewrite_amneziawg_item(result, host, port)
    elif protocol == "sudoku":
        _rewrite_sudoku_item(result, host, port)

    return result


def _live_client_item_v251(db, sub: Subscription, protocol: str, item: dict[str, Any]):
    if _ORIGINAL_LIVE_CLIENT_ITEM is None:
        raise RuntimeError("modern tunnel delivery binding is not initialized")

    result = _ORIGINAL_LIVE_CLIENT_ITEM(db, sub, protocol, item)
    protocol = str(protocol or "").strip().lower()
    if protocol not in MODERN_TUNNEL_PROTOCOLS or not isinstance(result, dict):
        return result

    try:
        node_id = int(result.get("node_id"))
    except (TypeError, ValueError):
        return result

    node = db.get(Node, node_id)
    if node is None or node.node_type != NodeType.EXIT:
        return result

    try:
        endpoint = _modern_tunnel_endpoint(
            db,
            node,
            protocol,
            int(sub.id),
        )
        if endpoint is None:
            return result
        host, port = endpoint
        return _rewrite_modern_item(result, protocol, host, port)
    except Exception:
        # Preserve the historical direct item instead of publishing a partially
        # rewritten credential when allocation/control-plane data is incomplete.
        return result


def apply_modern_protocol_tunnel_binding_v251() -> None:
    global _RUNTIME_APPLIED
    global _ORIGINAL_SERVICE_ROUTES_FOR_EXIT
    global _ORIGINAL_LIVE_CLIENT_ITEM

    if _RUNTIME_APPLIED:
        return

    # V87 must already own the route builder. Capture it, extend it additively,
    # and let Unified L3 V49 capture this final composite builder afterwards.
    _ORIGINAL_SERVICE_ROUTES_FOR_EXIT = tunnels._service_routes_for_exit
    tunnels._service_routes_for_exit = _service_routes_for_exit_v251

    # Delivery is read-time endpoint materialization. Existing encrypted
    # credentials and protocol identities stay untouched.
    _ORIGINAL_LIVE_CLIENT_ITEM = account_delivery._live_client_item
    account_delivery._live_client_item = _live_client_item_v251

    # Extend admin labels without changing the service-connections API shape.
    try:
        from . import tunnel_service_connections_admin_runtime as admin_runtime

        admin_runtime._PROTOCOL_TITLES.update({
            "hysteria2": "Hysteria2",
            "tuic": "TUIC",
            "anytls": "AnyTLS",
            "naive": "NaiveProxy",
            "shadowtls": "ShadowTLS",
            "snell": "Snell",
            "mieru": "Mieru",
            "trusttunnel": "TrustTunnel",
            "amneziawg": "AmneziaWG",
            "sudoku": "Sudoku",
        })
    except Exception:
        pass

    _RUNTIME_APPLIED = True
    print(
        "TWINPANEL_MODERN_PROTOCOL_TUNNEL_BINDING_V251_ACTIVE "
        "fixed=hysteria2,tuic,anytls,naive,shadowtls,snell,mieru,trusttunnel,amneziawg "
        "dynamic=sudoku authority=active-logical-tunnel delivery=iran-ingress",
        flush=True,
    )
