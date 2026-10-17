from __future__ import annotations

import base64
import json
import re
import shlex
from typing import Any
from urllib.parse import quote, urlencode

from . import (
    xray_modern_runtime,
    xray_node_domain_runtime,
    xray_profile_reconcile_v36,
    xray_public_delivery_runtime,
)
from .routers import account_delivery, provision, tunnels


# TWINPANEL_XRAY_TCP_TLS_V39
#
# Add a standard VLESS over TCP + TLS profile without exposing the legacy
# VLESS/plain listener to customers. The existing Xray certificate/domain is
# reused; UUIDs are never rotated. The public service route remains Iran-first:
# client -> Iran public port -> active tunnel -> Exit TCP/TLS listener.
#
# Exit target port: base Xray port + 5
# Iran public port: 28000 + Exit node id

PROFILE_TCP_TLS = "tcp_tls"
TCP_TLS_OFFSET = 5
TCP_TLS_PUBLIC_BASE = 28000

_runtime_applied = False
_original_ensure_modern_xray = None
_original_build_uri = None
_original_xray_account_modern = None
_original_service_routes = None
_original_required_profiles = None


def _tcp_tls_target_port(base_port: int) -> int:
    port = int(base_port) + TCP_TLS_OFFSET
    if not 1 <= port <= 65535:
        raise RuntimeError(f"invalid TCP TLS target port: {port}")
    return port


def _tcp_tls_public_port(exit_node_id: int) -> int:
    node_id = int(exit_node_id)
    if not 1 <= node_id <= 999:
        raise RuntimeError("TCP TLS public routing supports Exit IDs 1..999")
    port = TCP_TLS_PUBLIC_BASE + node_id
    if not 1 <= port <= 65535:
        raise RuntimeError(f"invalid TCP TLS public port: {port}")
    return port


def _effective_domain(node) -> str:
    return str(
        xray_node_domain_runtime._effective_xray_domain(node)
        if node is not None
        else ""
    ).strip().lower()


def _tcp_tls_config_script(
    *,
    port: int,
    domain: str,
    cert: str,
    key: str,
) -> str:
    return f'''
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

path = Path("/usr/local/etc/xray/config.json")
port = {int(port)!r}
domain = {domain!r}
cert = {cert!r}
key = {key!r}
tag = "vless-tcp-tls"

if not path.is_file():
    raise RuntimeError("Xray config is missing")
if not domain or not cert or not key:
    raise RuntimeError("TCP TLS requires a prepared TLS domain/certificate")
if not os.path.isfile(cert) or not os.path.isfile(key):
    raise RuntimeError("managed TLS certificate/key is missing")

with path.open("r", encoding="utf-8") as handle:
    doc = json.load(handle)

inbounds = doc.setdefault("inbounds", [])
if not isinstance(inbounds, list):
    raise RuntimeError("invalid Xray inbounds")

source_clients = []
for inbound in inbounds:
    if not isinstance(inbound, dict) or inbound.get("protocol") != "vless":
        continue
    clients = inbound.get("settings", {{}}).get("clients", [])
    if isinstance(clients, list):
        source_clients = [dict(item) for item in clients if isinstance(item, dict)]
        if source_clients:
            break

expected = {{
    "tag": tag,
    "listen": "0.0.0.0",
    "port": port,
    "protocol": "vless",
    "settings": {{
        "clients": source_clients,
        "decryption": "none",
    }},
    "streamSettings": {{
        "network": "tcp",
        "security": "tls",
        "tlsSettings": {{
            "serverName": domain,
            "minVersion": "1.2",
            "alpn": ["http/1.1"],
            "certificates": [
                {{
                    "certificateFile": cert,
                    "keyFile": key,
                }}
            ],
        }},
    }},
}}

changed = False
found_index = None
for index, inbound in enumerate(inbounds):
    if not isinstance(inbound, dict):
        continue
    if str(inbound.get("tag") or "") == tag:
        found_index = index
        break

if found_index is None:
    for inbound in inbounds:
        if not isinstance(inbound, dict):
            continue
        if int(inbound.get("port") or 0) == port:
            raise RuntimeError("TCP TLS target port collides with another Xray inbound")
    inbounds.append(expected)
    changed = True
else:
    current = inbounds[found_index]
    current_clients = current.get("settings", {{}}).get("clients", [])
    expected["settings"]["clients"] = (
        [dict(item) for item in current_clients if isinstance(item, dict)]
        if isinstance(current_clients, list)
        else source_clients
    )
    comparable_current = dict(current)
    comparable_expected = dict(expected)
    if comparable_current != comparable_expected:
        inbounds[found_index] = expected
        changed = True

if not changed:
    print(json.dumps({{"changed": False, "port": port}}, separators=(",", ":")))
    raise SystemExit(0)

tmp = Path("/usr/local/etc/xray/config.json.tcp-tls-v39")
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
    raise RuntimeError("TCP TLS candidate config test failed: " + (check.stderr or check.stdout or "")[-1200:])

stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
backup = Path(f"/usr/local/etc/xray/config.json.bak-tcp-tls-v39-{{stamp}}")
shutil.copy2(path, backup)
os.replace(tmp, path)
print(json.dumps({{"changed": True, "port": port, "backup": str(backup)}}, separators=(",", ":")))
'''


async def _ensure_modern_xray_v39(
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

    available = list(state.get("available_profiles") or [])
    if not bool(state.get("tls_enabled")):
        state["available_profiles"] = available
        return state

    domain = str(state.get("tls_domain") or _effective_domain(node)).strip().lower()
    cert = str(state.get("managed_cert") or "").strip()
    key = str(state.get("managed_key") or "").strip()
    target_port = _tcp_tls_target_port(int(base_port))

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
            f"TCP TLS port collision port={target_port} listener={occupied[:300]}"
        )

    script = _tcp_tls_config_script(
        port=target_port,
        domain=domain,
        cert=cert,
        key=key,
    )
    payload = base64.b64encode(script.encode()).decode()
    raw = await provision.cmd(
        conn,
        f"printf '%s' {shlex.quote(payload)} | base64 -d | python3",
    )

    try:
        result = json.loads(raw.strip().splitlines()[-1])
    except Exception as exc:
        raise RuntimeError("cannot parse TCP TLS config result: " + repr(exc)) from exc

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
                "TCP TLS listener verification failed; previous Xray config restored"
            )
    elif not await provision.listener(conn, target_port, "tcp"):
        raise RuntimeError("TCP TLS config exists but listener is not active")

    await provision.ufw_allow(conn, target_port, "tcp")

    if PROFILE_TCP_TLS not in available:
        available.append(PROFILE_TCP_TLS)
    state["available_profiles"] = available
    state["tcp_tls_port"] = target_port
    return state


def _build_uri_v39(
    *,
    profile: str,
    client_id: str,
    host: str,
    port: int,
    profile_name: str,
    state: dict[str, Any],
) -> str:
    assert _original_build_uri is not None

    if profile != PROFILE_TCP_TLS:
        return _original_build_uri(
            profile=profile,
            client_id=client_id,
            host=host,
            port=port,
            profile_name=profile_name,
            state=state,
        )

    domain = str(state.get("tls_domain") or "").strip()
    if not domain:
        raise RuntimeError("TCP TLS domain is unavailable")

    query = [
        ("encryption", "none"),
        ("security", "tls"),
        ("type", "tcp"),
        ("sni", domain),
        ("fp", "chrome"),
        ("alpn", "http/1.1"),
    ]
    label = quote(f"{profile_name}-VLESS-TCP-TLS", safe="")
    return (
        f"vless://{client_id}@{host}:{int(port)}"
        f"?{urlencode(query)}#{label}"
    )


async def _xray_account_modern_v39(
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

    profiles = item.get("profiles")
    if not isinstance(profiles, list):
        return item
    if any(
        isinstance(profile, dict)
        and str(profile.get("id") or "") == PROFILE_TCP_TLS
        for profile in profiles
    ):
        return item

    domain = _effective_domain(node)
    if not domain or not bool(item.get("tls_available")):
        return item

    host, public_port = xray_modern_runtime._profile_endpoint(
        db,
        node,
        PROFILE_TCP_TLS,
    )

    username_part = account_delivery._download_filename_part(
        sub.account_username
        or account_delivery._safe_username(sub, user),
        f"user{sub.id}",
    )
    country_part = account_delivery._country_download_name(node)
    profile_name = f"{username_part}-{country_part}"

    uri = _build_uri_v39(
        profile=PROFILE_TCP_TLS,
        client_id=client_id,
        host=host,
        port=public_port,
        profile_name=profile_name,
        state={"tls_domain": domain},
    )

    profiles.append(
        {
            "id": PROFILE_TCP_TLS,
            "title": "VLESS TCP TLS",
            "recommended": False,
            "security": "tls",
            "transport": "tcp",
            "server": host,
            "port": int(public_port),
            "uri": uri,
            "sni": domain,
        }
    )

    return item


def _service_routes_v39(db, exit_node, exit_tunnel_ip: str) -> list[dict]:
    assert _original_service_routes is not None

    routes = list(_original_service_routes(db, exit_node, exit_tunnel_ip))

    cfg = (
        db.query(xray_modern_runtime.NodeProtocolConfig)
        .filter(
            xray_modern_runtime.NodeProtocolConfig.node_id == exit_node.id,
            xray_modern_runtime.NodeProtocolConfig.protocol == "v2ray",
        )
        .first()
    )
    if not cfg or xray_modern_runtime._enum_value(cfg.status) != "online":
        return routes

    domain = _effective_domain(exit_node)
    if not domain:
        return routes

    public_port = _tcp_tls_public_port(int(exit_node.id))
    if any(
        isinstance(route, dict)
        and str(route.get("protocol") or "") == "v2ray"
        and int(route.get("public_port") or 0) == public_port
        for route in routes
    ):
        return routes

    base_port = int(cfg.port or account_delivery.DEFAULT_PORTS["v2ray"])
    routes.append(
        {
            "protocol": "v2ray",
            "profile": PROFILE_TCP_TLS,
            "exit_node_id": int(exit_node.id),
            "public_port": public_port,
            "target_ip": exit_tunnel_ip,
            "target_port": _tcp_tls_target_port(base_port),
            "transport": "tcp",
            "client_subnet": None,
        }
    )
    return routes


def _required_profiles_v39(node) -> set[str]:
    assert _original_required_profiles is not None
    required = set(_original_required_profiles(node))
    if _effective_domain(node):
        required.add(PROFILE_TCP_TLS)
    return required


def apply_xray_tcp_tls_v39() -> None:
    global _runtime_applied
    global _original_ensure_modern_xray
    global _original_build_uri
    global _original_xray_account_modern
    global _original_service_routes
    global _original_required_profiles

    if _runtime_applied:
        return

    xray_modern_runtime.PROFILE_TCP_TLS = PROFILE_TCP_TLS
    xray_modern_runtime.PROFILE_META[PROFILE_TCP_TLS] = {
        "offset": TCP_TLS_OFFSET,
        "public_base": TCP_TLS_PUBLIC_BASE,
        "title": "VLESS TCP TLS",
        "transport": "tcp",
        "security": "tls",
        "recommended": False,
    }
    xray_modern_runtime._TLS_PROFILES.add(PROFILE_TCP_TLS)

    _original_ensure_modern_xray = xray_modern_runtime._ensure_modern_xray
    _original_build_uri = xray_modern_runtime._build_uri
    _original_xray_account_modern = xray_modern_runtime._xray_account_modern
    _original_service_routes = tunnels._service_routes_for_exit
    _original_required_profiles = xray_profile_reconcile_v36._required_profiles

    xray_modern_runtime._ensure_modern_xray = _ensure_modern_xray_v39
    xray_modern_runtime._build_uri = _build_uri_v39
    xray_modern_runtime._xray_account_modern = _xray_account_modern_v39
    account_delivery._xray = _xray_account_modern_v39
    tunnels._service_routes_for_exit = _service_routes_v39
    xray_profile_reconcile_v36._required_profiles = _required_profiles_v39

    xray_public_delivery_runtime._PROFILE_LABELS[PROFILE_TCP_TLS] = "TCP TLS"

    _runtime_applied = True

    print(
        "TWINPANEL_XRAY_TCP_TLS_V39_ACTIVE "
        "exit_offset=5 public_base=28000 tls=1 uuid_preserved=1",
        flush=True,
    )
