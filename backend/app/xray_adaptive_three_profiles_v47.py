from __future__ import annotations

import base64
import json
import shlex
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from . import (
    tunnel_service_connections_admin_runtime,
    xray_customer_profile_policy_v30 as policy_v30,
    xray_customer_xhttp_v46,
    xray_modern_admin,
    xray_modern_repair_runtime,
    xray_modern_runtime,
    xray_profile_reconcile_v36,
    xray_public_delivery_runtime,
)
from .models import Node, NodeProtocolConfig
from .routers import account_delivery, provision, tunnels
from .xray_tcp_tls_v39 import PROFILE_TCP_TLS


# TWINPANEL_XRAY_ADAPTIVE_THREE_PROFILES_V47
#
# Exactly three real customer profiles per Xray Exit:
#
#   TLS identity ready:
#     WebSocket TLS -> XHTTP Reality -> TCP TLS
#
#   No TLS identity:
#     XHTTP Reality -> gRPC Reality -> TCP Reality
#
# TCP Reality is domain-independent and reuses the existing stable REALITY
# private/public key, server name and XHTTP short-id. UUIDs are never rotated.
# XHTTP remains on V46's collision-free target offset (+1004). TCP Reality uses
# the next Xray-private target (+1005) and Iran public range 38000..38999.
# 28000..37999 belongs to modern protocols; 40000..49999 belongs to Sudoku.

PROFILE_TCP_REALITY = "tcp_reality"
TCP_REALITY_TARGET_OFFSET = 1005
TCP_REALITY_PUBLIC_BASE = 38000

_runtime_applied = False
_original_ensure_modern_xray = None
_original_xray_account_modern = None
_original_service_routes = None
_original_admin_profile_rows = None
_original_admin_status_remote = None


def _effective_domain(node: Node | None) -> str:
    if node is None:
        return ""
    return str(
        getattr(node, "xray_domain", None)
        or getattr(node, "public_domain", None)
        or ""
    ).strip().lower()


def _tcp_reality_target_port(base_port: int) -> int:
    port = int(base_port) + TCP_REALITY_TARGET_OFFSET
    if not 1 <= port <= 65535:
        raise RuntimeError(f"invalid TCP Reality target port: {port}")
    return port


def _tcp_reality_public_port(exit_node_id: int) -> int:
    node_id = int(exit_node_id)
    if not 1 <= node_id <= 999:
        raise RuntimeError("TCP Reality public routing supports Exit IDs 1..999")
    port = TCP_REALITY_PUBLIC_BASE + node_id
    if not 1 <= port <= 65535:
        raise RuntimeError(f"invalid TCP Reality public port: {port}")
    return port


def _tcp_reality_config_script(port: int) -> str:
    return f'''
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

config_path = Path("/usr/local/etc/xray/config.json")
state_path = Path("/usr/local/etc/xray/twinpanel-modern-state.json")
port = {int(port)!r}
tag = "vless-tcp-reality"

if not config_path.is_file():
    raise RuntimeError("Xray config is missing")
if not state_path.is_file():
    raise RuntimeError("Xray modern state is missing")

with state_path.open("r", encoding="utf-8") as handle:
    state = json.load(handle)

private_key = str(state.get("reality_private_key") or "").strip()
target = str(state.get("reality_target") or "").strip()
server_name = str(state.get("reality_server_name") or "").strip()
short_id = str(state.get("short_id_xhttp") or "").strip()

if not private_key or not target or not server_name or not short_id:
    raise RuntimeError("Xray REALITY state is incomplete")

with config_path.open("r", encoding="utf-8") as handle:
    doc = json.load(handle)

inbounds = doc.setdefault("inbounds", [])
if not isinstance(inbounds, list):
    raise RuntimeError("invalid Xray inbounds")

clients = []
for inbound in inbounds:
    if not isinstance(inbound, dict) or inbound.get("protocol") != "vless":
        continue
    raw_clients = inbound.get("settings", {{}}).get("clients", [])
    if isinstance(raw_clients, list) and raw_clients:
        clients = [dict(item) for item in raw_clients if isinstance(item, dict)]
        break

expected = {{
    "tag": tag,
    "listen": "0.0.0.0",
    "port": port,
    "protocol": "vless",
    "settings": {{
        "clients": clients,
        "decryption": "none",
    }},
    "streamSettings": {{
        "network": "tcp",
        "security": "reality",
        "realitySettings": {{
            "show": False,
            "target": target,
            "xver": 0,
            "serverNames": [server_name],
            "privateKey": private_key,
            "shortIds": [short_id],
        }},
    }},
}}

found = None
for index, inbound in enumerate(inbounds):
    if not isinstance(inbound, dict):
        continue
    if str(inbound.get("tag") or "") == tag:
        found = index
        break

changed = False
if found is None:
    for inbound in inbounds:
        if not isinstance(inbound, dict):
            continue
        if int(inbound.get("port") or 0) == port:
            raise RuntimeError("TCP Reality target port collides with another Xray inbound")
    inbounds.append(expected)
    changed = True
else:
    current = inbounds[found]
    current_clients = current.get("settings", {{}}).get("clients", [])
    if isinstance(current_clients, list):
        expected["settings"]["clients"] = [
            dict(item) for item in current_clients if isinstance(item, dict)
        ]
    if current != expected:
        inbounds[found] = expected
        changed = True

if not changed:
    print(json.dumps({{"changed": False, "port": port}}, separators=(",", ":")))
    raise SystemExit(0)

tmp = Path("/usr/local/etc/xray/config.json.tcp-reality-v47.json")
with tmp.open("w", encoding="utf-8") as handle:
    json.dump(doc, handle, ensure_ascii=False, indent=2)
    handle.write("\\n")

check = subprocess.run(
    ["/usr/local/bin/xray", "run", "-test", "-config", str(tmp)],
    text=True,
    capture_output=True,
    check=False,
)
if check.returncode != 0:
    tmp.unlink(missing_ok=True)
    raise RuntimeError(
        "TCP Reality candidate config test failed: "
        + (check.stderr or check.stdout or "")[-1200:]
    )

stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
backup = Path(f"/usr/local/etc/xray/config.json.bak-tcp-reality-v47-{{stamp}}")
shutil.copy2(config_path, backup)
os.replace(tmp, config_path)
print(json.dumps({{"changed": True, "port": port, "backup": str(backup)}}, separators=(",", ":")))
'''


async def _ensure_modern_xray_v47(
    conn,
    base_port: int,
    node=None,
    *,
    bootstrap_done: bool = False,
):
    assert _original_ensure_modern_xray is not None

    state = await _original_ensure_modern_xray(
        conn,
        int(base_port),
        node,
        bootstrap_done=bootstrap_done,
    )

    # TLS-ready nodes use WS + XHTTP + TCP TLS. Keep TCP Reality internal/off.
    if _effective_domain(node):
        return state

    target_port = _tcp_reality_target_port(int(base_port))
    occupied = (
        await provision.cmd(
            conn,
            (
                "ss -H -lntp 2>/dev/null "
                f"| awk '$4 ~ /:{target_port}$/ {{print}}' | head -1"
            ),
            check=False,
        )
    ).strip()

    if occupied and "xray" not in occupied.lower():
        raise RuntimeError(
            f"TCP Reality port collision port={target_port} listener={occupied[:300]}"
        )

    script = _tcp_reality_config_script(target_port)
    payload = base64.b64encode(script.encode()).decode()
    raw = await provision.cmd(
        conn,
        f"printf '%s' {shlex.quote(payload)} | base64 -d | python3",
    )

    try:
        result = json.loads(raw.strip().splitlines()[-1])
    except Exception as exc:
        raise RuntimeError("cannot parse TCP Reality config result: " + repr(exc)) from exc

    if bool(result.get("changed")):
        backup = str(result.get("backup") or "").strip()
        await provision.cmd(conn, "systemctl restart xray")
        service_ok = await provision.active(conn, "xray")
        listener_ok = await provision.listener(conn, target_port, "tcp")
        if not (service_ok and listener_ok):
            if backup:
                await provision.cmd(
                    conn,
                    (
                        f"if [ -f {shlex.quote(backup)} ]; then "
                        f"cp -a {shlex.quote(backup)} /usr/local/etc/xray/config.json; "
                        "systemctl restart xray; fi"
                    ),
                    check=False,
                )
            raise RuntimeError(
                "TCP Reality listener verification failed; previous Xray config restored"
            )
    elif not await provision.listener(conn, target_port, "tcp"):
        raise RuntimeError("TCP Reality config exists but listener is not active")

    await provision.ufw_allow(conn, target_port, "tcp")

    available = list(state.get("available_profiles") or [])
    if PROFILE_TCP_REALITY not in available:
        available.append(PROFILE_TCP_REALITY)
    state["available_profiles"] = available
    state["tcp_reality_port"] = target_port
    return state


def _reality_values_from_xhttp(
    profiles: list[dict[str, Any]],
) -> tuple[str, str, str]:
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        if str(profile.get("id") or "").strip().lower() != xray_modern_runtime.PROFILE_XHTTP:
            continue
        uri = str(profile.get("uri") or "").strip()
        if not uri:
            continue
        parsed = urlsplit(uri)
        query = parse_qs(parsed.query)
        sni = str((query.get("sni") or [""])[0]).strip()
        public_key = str((query.get("pbk") or [""])[0]).strip()
        short_id = str((query.get("sid") or [""])[0]).strip()
        if sni and public_key and short_id:
            return sni, public_key, short_id
    raise RuntimeError("XHTTP REALITY identity is unavailable")


def _tcp_reality_uri(
    *,
    client_id: str,
    host: str,
    port: int,
    profile_name: str,
    sni: str,
    public_key: str,
    short_id: str,
) -> str:
    query = urlencode(
        [
            ("encryption", "none"),
            ("security", "reality"),
            ("type", "tcp"),
            ("sni", sni),
            ("fp", "chrome"),
            ("pbk", public_key),
            ("sid", short_id),
        ]
    )
    label = quote(f"{profile_name}-VLESS-TCP-REALITY", safe="")
    return f"vless://{client_id}@{host}:{int(port)}?{query}#{label}"


async def _xray_account_modern_v47(
    db,
    node,
    sub,
    user,
    client_id: str,
):
    assert _original_xray_account_modern is not None

    item = await _original_xray_account_modern(
        db,
        node,
        sub,
        user,
        client_id,
    )

    if _effective_domain(node):
        return item

    profiles = item.get("profiles")
    if not isinstance(profiles, list):
        return item

    if any(
        isinstance(profile, dict)
        and str(profile.get("id") or "").strip().lower() == PROFILE_TCP_REALITY
        for profile in profiles
    ):
        return item

    sni, public_key, short_id = _reality_values_from_xhttp(profiles)
    host, public_port = xray_modern_runtime._profile_endpoint(
        db,
        node,
        PROFILE_TCP_REALITY,
    )

    username_part = account_delivery._download_filename_part(
        sub.account_username
        or account_delivery._safe_username(sub, user),
        f"user{sub.id}",
    )
    country_part = account_delivery._country_download_name(node)
    profile_name = f"{username_part}-{country_part}"

    uri = _tcp_reality_uri(
        client_id=client_id,
        host=host,
        port=public_port,
        profile_name=profile_name,
        sni=sni,
        public_key=public_key,
        short_id=short_id,
    )

    profiles.append(
        {
            "id": PROFILE_TCP_REALITY,
            "title": "VLESS TCP Reality",
            "recommended": False,
            "security": "reality",
            "transport": "tcp",
            "server": host,
            "port": int(public_port),
            "uri": uri,
            "sni": sni,
        }
    )
    return item


def _service_routes_v47(
    db,
    exit_node,
    exit_tunnel_ip: str,
) -> list[dict]:
    assert _original_service_routes is not None

    routes = list(_original_service_routes(db, exit_node, exit_tunnel_ip))

    if _effective_domain(exit_node):
        return routes

    cfg = (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == int(exit_node.id),
            NodeProtocolConfig.protocol == "v2ray",
        )
        .first()
    )
    if (
        not cfg
        or str(getattr(cfg.status, "value", cfg.status) or "").lower() != "online"
    ):
        return routes

    public_port = _tcp_reality_public_port(int(exit_node.id))
    if any(
        isinstance(route, dict)
        and str(route.get("protocol") or "") == "v2ray"
        and str(route.get("profile") or "") == PROFILE_TCP_REALITY
        for route in routes
    ):
        return routes

    base_port = int(cfg.port or account_delivery.DEFAULT_PORTS["v2ray"])
    routes.append(
        {
            "protocol": "v2ray",
            "profile": PROFILE_TCP_REALITY,
            "exit_node_id": int(exit_node.id),
            "public_port": public_port,
            "target_ip": exit_tunnel_ip,
            "target_port": _tcp_reality_target_port(base_port),
            "transport": "tcp",
            "client_subnet": None,
        }
    )
    return routes


def _required_profiles_v47(node: Node) -> set[str]:
    if _effective_domain(node):
        return {
            xray_modern_runtime.PROFILE_WS,
            xray_modern_runtime.PROFILE_XHTTP,
            PROFILE_TCP_TLS,
        }
    return {
        xray_modern_runtime.PROFILE_XHTTP,
        xray_modern_runtime.PROFILE_GRPC,
        PROFILE_TCP_REALITY,
    }


def _customer_order_for_item(item: dict[str, Any]) -> tuple[str, ...]:
    raw_profiles = item.get("profiles")
    if not isinstance(raw_profiles, list):
        return ()

    ids = {
        str(profile.get("id") or "").strip().lower()
        for profile in raw_profiles
        if isinstance(profile, dict) and str(profile.get("uri") or "").strip()
    }

    tls_order = (
        xray_modern_runtime.PROFILE_WS,
        xray_modern_runtime.PROFILE_XHTTP,
        PROFILE_TCP_TLS,
    )
    if all(profile in ids for profile in tls_order):
        return tls_order

    return (
        xray_modern_runtime.PROFILE_XHTTP,
        xray_modern_runtime.PROFILE_GRPC,
        PROFILE_TCP_REALITY,
    )


def _customer_profiles_v47(item: dict[str, Any]) -> list[dict[str, Any]]:
    raw_profiles = item.get("profiles")
    if not isinstance(raw_profiles, list):
        return []

    by_id = {
        str(profile.get("id") or "").strip().lower(): dict(profile)
        for profile in raw_profiles
        if isinstance(profile, dict) and str(profile.get("uri") or "").strip()
    }
    return [
        by_id[profile_id]
        for profile_id in _customer_order_for_item(item)
        if profile_id in by_id
    ]


def _customer_xray_item_v47(
    db,
    item: dict[str, Any],
) -> dict[str, Any] | None:
    raw_profiles = item.get("profiles")
    if not isinstance(raw_profiles, list):
        return dict(item)

    try:
        node_id = int(item.get("node_id") or 0)
    except (TypeError, ValueError):
        return None

    node = db.get(Node, node_id)
    if node is None:
        return None

    desired = (
        (
            xray_modern_runtime.PROFILE_WS,
            xray_modern_runtime.PROFILE_XHTTP,
            PROFILE_TCP_TLS,
        )
        if _effective_domain(node)
        else (
            xray_modern_runtime.PROFILE_XHTTP,
            xray_modern_runtime.PROFILE_GRPC,
            PROFILE_TCP_REALITY,
        )
    )

    by_id: dict[str, dict[str, Any]] = {}
    for raw_profile in raw_profiles:
        if not isinstance(raw_profile, dict):
            continue
        profile_id = str(raw_profile.get("id") or "").strip().lower()
        if profile_id not in desired:
            continue
        uri = str(raw_profile.get("uri") or "").strip()
        if not uri:
            continue
        try:
            host, port = policy_v30._profile_endpoint_v261(
                db,
                node,
                profile_id,
                item,
            )
        except Exception:
            continue
        profile = dict(raw_profile)
        profile["server"] = host
        profile["server_ip"] = host
        profile["port"] = int(port)
        profile["uri"] = policy_v30._rewrite_vless_authority_v261(
            uri,
            host,
            int(port),
        )
        profile["qr"] = account_delivery._qr_data_uri(profile["uri"])
        by_id[profile_id] = profile

    profiles = [
        by_id[profile_id]
        for profile_id in desired
        if profile_id in by_id
    ]

    # Exact-three contract: fail closed until reconciliation produces all three.
    if len(profiles) != 3:
        return None

    selected = profiles[0]
    result = dict(item)
    result["profiles"] = profiles
    result["server"] = selected["server"]
    result["server_ip"] = selected["server"]
    result["port"] = int(selected["port"])
    result["uri"] = selected["uri"]
    result["qr"] = selected["qr"]
    result["profile"] = str(selected.get("id") or "")

    for key in ("sni", "security", "transport"):
        if selected.get(key) is not None:
            result[key] = selected.get(key)

    return result


def _admin_profile_rows_v47(node, base_port: int) -> list[dict[str, Any]]:
    assert _original_admin_profile_rows is not None

    rows = list(_original_admin_profile_rows(node, int(base_port)))
    by_id = {
        str(row.get("id") or "").strip().lower(): dict(row)
        for row in rows
        if isinstance(row, dict)
    }

    by_id[PROFILE_TCP_REALITY] = {
        "id": PROFILE_TCP_REALITY,
        "title": "VLESS TCP Reality",
        "security": "reality",
        "transport": "tcp",
        "recommended": False,
        "requires_tls_domain": False,
        "target_port": _tcp_reality_target_port(int(base_port)),
        "tunnel_public_port": _tcp_reality_public_port(int(node.id)),
    }

    desired = (
        (
            xray_modern_runtime.PROFILE_WS,
            xray_modern_runtime.PROFILE_XHTTP,
            PROFILE_TCP_TLS,
        )
        if _effective_domain(node)
        else (
            xray_modern_runtime.PROFILE_XHTTP,
            xray_modern_runtime.PROFILE_GRPC,
            PROFILE_TCP_REALITY,
        )
    )
    return [by_id[profile] for profile in desired if profile in by_id]


async def _admin_status_remote_v47(conn, base_port: int) -> dict[str, Any]:
    assert _original_admin_status_remote is not None

    state = dict(await _original_admin_status_remote(conn, int(base_port)))
    profiles = dict(state.get("profiles") or {})
    profiles[PROFILE_TCP_REALITY] = bool(
        await provision.listener(
            conn,
            _tcp_reality_target_port(int(base_port)),
            "tcp",
        )
    )
    state["profiles"] = profiles
    return state


def apply_xray_adaptive_three_profiles_v47() -> None:
    global _runtime_applied
    global _original_ensure_modern_xray
    global _original_xray_account_modern
    global _original_service_routes
    global _original_admin_profile_rows
    global _original_admin_status_remote

    if _runtime_applied:
        return

    # Restore V46 first: XHTTP customer visibility + collision-free +1004 target.
    xray_customer_xhttp_v46.apply_xray_customer_xhttp_v46()

    xray_modern_runtime.PROFILE_TCP_REALITY = PROFILE_TCP_REALITY
    xray_modern_runtime.PROFILE_META[PROFILE_TCP_REALITY] = {
        "offset": TCP_REALITY_TARGET_OFFSET,
        "public_base": TCP_REALITY_PUBLIC_BASE,
        "title": "VLESS TCP Reality",
        "transport": "tcp",
        "security": "reality",
        "recommended": False,
    }

    _original_ensure_modern_xray = xray_modern_runtime._ensure_modern_xray
    _original_xray_account_modern = xray_modern_runtime._xray_account_modern
    _original_service_routes = tunnels._service_routes_for_exit
    _original_admin_profile_rows = xray_modern_admin._profile_rows
    _original_admin_status_remote = xray_modern_admin._status_remote

    xray_modern_runtime._ensure_modern_xray = _ensure_modern_xray_v47
    xray_modern_runtime._xray_account_modern = _xray_account_modern_v47
    account_delivery._xray = _xray_account_modern_v47
    tunnels._service_routes_for_exit = _service_routes_v47

    xray_profile_reconcile_v36._required_profiles = _required_profiles_v47

    # V30 wrappers resolve this callable dynamically.
    policy_v30._customer_xray_item_v261 = _customer_xray_item_v47

    # Public /connect is dynamic per item: no fake TLS on domainless nodes.
    xray_public_delivery_runtime._customer_profiles = _customer_profiles_v47
    xray_public_delivery_runtime._PROFILE_LABELS[PROFILE_TCP_REALITY] = "TCP Reality"

    # Keep admin profile/status surfaces aligned with the actual runtime.
    xray_modern_admin._profile_rows = _admin_profile_rows_v47
    xray_modern_admin._status_remote = _admin_status_remote_v47
    xray_modern_repair_runtime._ensure_modern_xray = _ensure_modern_xray_v47
    tunnel_service_connections_admin_runtime._current_xray_status_remote = (
        _admin_status_remote_v47
    )
    tunnel_service_connections_admin_runtime._XRAY_PROFILE_TITLES[
        PROFILE_TCP_REALITY
    ] = "VLESS TCP Reality"

    # V30 Service Connections filter reads this global at request time.
    policy_v30.ADMIN_ROUTE_PROFILE_IDS = frozenset(
        {
            *policy_v30.ADMIN_ROUTE_PROFILE_IDS,
            PROFILE_TCP_REALITY,
            xray_modern_runtime.PROFILE_XHTTP,
            xray_modern_runtime.PROFILE_GRPC,
        }
    )

    _runtime_applied = True
    print(
        "TWINPANEL_XRAY_ADAPTIVE_THREE_PROFILES_V47_ACTIVE "
        "tls_ready=websocket_tls,xhttp_reality,tcp_tls "
        "no_tls=xhttp_reality,grpc_reality,tcp_reality "
        "tcp_reality_target_offset=1005 "
        "tcp_reality_public_base=38000 "
        "uuid_preserved=1 reality_identity_reused=1 fake_tls=0",
        flush=True,
    )
