from __future__ import annotations

import base64
import json
import os
import re
import shlex
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .deps import get_current_user, require_admin
from .models import (
    Node,
    NodeProtocolConfig,
    NodeType,
    ProtocolCredential,
    Subscription,
    SubscriptionProtocol,
    User,
)


router = APIRouter(
    prefix="/v1/xray-modern",
    tags=["xray-modern"],
)


# TWINPANEL_XRAY_MODERN_RUNTIME_V2
#
# Existing VLESS RAW/plain remains on the legacy Xray port for old links.
# New customer-facing profiles use separate listeners and never expose the
# legacy plain URI to newly provisioned credentials.
#
# Restricted-network compatibility order:
#   1. WebSocket + TLS (when a valid Exit domain/certificate exists)
#   2. XHTTP + REALITY (modern no-domain profile)
#   3. HTTPUpgrade + TLS (when TLS is available)
#   4. gRPC + REALITY (last-resort fallback)
#
# Xray supports VLESS over WS/XHTTP/HTTPUpgrade/gRPC. REALITY is compatible
# with XHTTP/gRPC, while WS/HTTPUpgrade use ordinary TLS.

XRAY_REALITY_TARGET = (
    os.getenv(
        "TWINPANEL_XRAY_REALITY_TARGET",
        "www.microsoft.com:443",
    ).strip()
    or "www.microsoft.com:443"
)

XRAY_REALITY_SERVER_NAME = (
    os.getenv(
        "TWINPANEL_XRAY_REALITY_SERVER_NAME",
        XRAY_REALITY_TARGET.split(":", 1)[0],
    ).strip()
    or XRAY_REALITY_TARGET.split(":", 1)[0]
)

PROFILE_XHTTP = "xhttp_reality"
PROFILE_GRPC = "grpc_reality"
PROFILE_WS = "websocket_tls"
PROFILE_HTTPUPGRADE = "httpupgrade_tls"

PROFILE_META: dict[str, dict[str, Any]] = {
    PROFILE_XHTTP: {
        "offset": 1,
        "public_base": 23100,
        "title": "VLESS XHTTP REALITY",
        "transport": "xhttp",
        "security": "reality",
        "recommended": True,
    },
    PROFILE_GRPC: {
        "offset": 2,
        "public_base": 23200,
        "title": "VLESS gRPC REALITY",
        "transport": "grpc",
        "security": "reality",
        "recommended": False,
    },
    PROFILE_WS: {
        "offset": 3,
        "public_base": 23300,
        "title": "VLESS WebSocket TLS",
        "transport": "websocket",
        "security": "tls",
        "recommended": True,
    },
    PROFILE_HTTPUPGRADE: {
        "offset": 4,
        "public_base": 23400,
        "title": "VLESS HTTPUpgrade TLS",
        "transport": "httpupgrade",
        "security": "tls",
        "recommended": False,
    },
}

_TLS_PROFILES = {
    PROFILE_WS,
    PROFILE_HTTPUPGRADE,
}

_originals: dict[str, Any] = {}
_runtime_applied = False


def _enum_value(value: Any) -> str:
    return str(
        getattr(value, "value", value)
        or ""
    ).strip().lower()


def _clean_domain(value: Any) -> str:
    domain = str(value or "").strip().lower()
    domain = re.sub(r"^https?://", "", domain).split("/")[0].strip()

    if ":" in domain:
        domain = domain.split(":", 1)[0]

    if not re.fullmatch(
        r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?",
        domain,
    ):
        return ""

    return domain


def _target_port(base_port: int, profile: str) -> int:
    port = int(base_port) + int(PROFILE_META[str(profile)]["offset"])

    if not 1 <= port <= 65535:
        raise RuntimeError(f"invalid Xray target port: {port}")

    return port


def _public_port(exit_node_id: int, profile: str) -> int:
    node_id = int(exit_node_id)

    if not 1 <= node_id <= 999:
        raise RuntimeError(
            "Xray modern public routing supports Exit IDs 1..999"
        )

    port = int(PROFILE_META[str(profile)]["public_base"]) + node_id

    if not 1 <= port <= 65535:
        raise RuntimeError(f"invalid Xray public port: {port}")

    return port


def _profile_endpoint(
    db: Session,
    node: Node,
    profile: str,
) -> tuple[str, int]:
    from .routers import account_delivery

    host, legacy_port = account_delivery._tunnel_access_endpoint(
        db,
        node,
        "v2ray",
    )

    base_port = account_delivery._port(
        db,
        node.id,
        "v2ray",
    )

    expected_tunnel_port = 23000 + int(node.id)

    # Active/assigned Iran ingress. Reuse the same logical tunnel and only
    # publish a different service port; transport internals stay hidden.
    if int(legacy_port) == expected_tunnel_port:
        return host, _public_port(node.id, profile)

    # No Iran assignment: preserve the existing direct-Exit fallback model.
    return host, _target_port(base_port, profile)


def _build_uri(
    *,
    profile: str,
    client_id: str,
    host: str,
    port: int,
    profile_name: str,
    state: dict[str, Any],
) -> str:
    query: list[tuple[str, str]] = [
        ("encryption", "none"),
    ]

    if profile == PROFILE_XHTTP:
        query.extend(
            [
                ("security", "reality"),
                ("type", "xhttp"),
                ("path", str(state["xhttp_path"])),
                # Explicit stream-one avoids recent client auto-mode
                # regressions while the server accepts stream-one via
                # stream-up compatibility.
                ("mode", "stream-one"),
                ("sni", str(state["reality_server_name"])),
                ("fp", "chrome"),
                ("pbk", str(state["reality_password"])),
                ("sid", str(state["short_id_xhttp"])),
            ]
        )

    elif profile == PROFILE_GRPC:
        query.extend(
            [
                ("security", "reality"),
                ("type", "grpc"),
                ("serviceName", str(state["grpc_service"])),
                ("sni", str(state["reality_server_name"])),
                ("fp", "chrome"),
                ("pbk", str(state["reality_password"])),
                ("sid", str(state["short_id_grpc"])),
            ]
        )

    elif profile == PROFILE_WS:
        domain = str(state.get("tls_domain") or "").strip()
        if not domain:
            raise RuntimeError("WebSocket TLS domain is unavailable")

        query.extend(
            [
                ("security", "tls"),
                ("type", "ws"),
                ("sni", domain),
                ("host", domain),
                ("path", str(state["ws_path"])),
                ("fp", "chrome"),
                ("alpn", "http/1.1"),
            ]
        )

    elif profile == PROFILE_HTTPUPGRADE:
        domain = str(state.get("tls_domain") or "").strip()
        if not domain:
            raise RuntimeError("HTTPUpgrade TLS domain is unavailable")

        query.extend(
            [
                ("security", "tls"),
                ("type", "httpupgrade"),
                ("sni", domain),
                ("host", domain),
                ("path", str(state["httpupgrade_path"])),
                ("fp", "chrome"),
                ("alpn", "http/1.1"),
            ]
        )

    else:
        raise RuntimeError(f"unknown Xray modern profile: {profile}")

    label = (
        str(profile_name)
        + "-"
        + str(PROFILE_META[profile]["title"]).replace(" ", "-")
    )

    return (
        f"vless://{client_id}@{host}:{int(port)}"
        f"?{urlencode(query)}"
        f"#{quote(label, safe='')}"
    )


def _state_generator_script(domain: str) -> str:
    return f'''
import json
import os
import pwd
import secrets
import shutil
import subprocess
from pathlib import Path

domain = {domain!r}
reality_target = {XRAY_REALITY_TARGET!r}
reality_server_name = {XRAY_REALITY_SERVER_NAME!r}

state_path = Path(
    "/usr/local/etc/xray/twinpanel-modern-state.json"
)
state = {{}}

if state_path.exists():
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError("invalid Xray modern state: " + repr(exc))


def parse_x25519(output):
    parsed = {{}}
    for raw in str(output or "").splitlines():
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        key = key.strip().lower().replace(" ", "").replace("_", "")
        value = value.strip()
        if not value:
            continue
        if key in {{"privatekey", "private"}}:
            parsed["private_key"] = value
        elif key in {{"password", "publickey", "public"}}:
            parsed["password"] = value
    return parsed


private_key = str(state.get("reality_private_key") or "").strip()
password = str(state.get("reality_password") or "").strip()

if not private_key:
    result = subprocess.run(
        ["/usr/local/bin/xray", "x25519"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "xray x25519 failed: "
            + (result.stderr or result.stdout or "")
        )
    parsed = parse_x25519(result.stdout + "\\n" + result.stderr)
    private_key = str(parsed.get("private_key") or "").strip()
    password = str(parsed.get("password") or "").strip()

if private_key and not password:
    result = subprocess.run(
        ["/usr/local/bin/xray", "x25519", "-i", private_key],
        text=True,
        capture_output=True,
        check=False,
    )
    parsed = parse_x25519(result.stdout + "\\n" + result.stderr)
    password = str(parsed.get("password") or "").strip()

if not private_key or not password:
    raise RuntimeError("REALITY key generation/derivation failed")


def stable_hex(key, bytes_count):
    value = str(state.get(key) or "").strip().lower()
    expected = bytes_count * 2
    if (
        len(value) != expected
        or any(c not in "0123456789abcdef" for c in value)
    ):
        value = secrets.token_hex(bytes_count)
    return value


def stable_path(key, prefix):
    value = str(state.get(key) or "").strip()
    if (
        not value.startswith("/")
        or len(value) < 8
        or len(value) > 120
        or any(c.isspace() for c in value)
    ):
        value = "/" + prefix + "-" + secrets.token_hex(8)
    return value


short_id_xhttp = stable_hex("short_id_xhttp", 8)
short_id_grpc = stable_hex("short_id_grpc", 8)
if short_id_grpc == short_id_xhttp:
    short_id_grpc = secrets.token_hex(8)

xhttp_path = stable_path("xhttp_path", "xh")
ws_path = stable_path("ws_path", "ws")
httpupgrade_path = stable_path("httpupgrade_path", "hu")

grpc_service = str(state.get("grpc_service") or "").strip()
if (
    not grpc_service
    or len(grpc_service) > 80
    or not all(c.isalnum() or c in "-_" for c in grpc_service)
):
    grpc_service = "tpgrpc-" + secrets.token_hex(8)


tls_enabled = False
source_cert = ""
source_key = ""
managed_cert = ""
managed_key = ""
service_user = "root"

if domain:
    candidates = [
        (
            f"/etc/letsencrypt/live/{{domain}}/fullchain.pem",
            f"/etc/letsencrypt/live/{{domain}}/privkey.pem",
        ),
        (
            f"/root/.acme.sh/{{domain}}_ecc/fullchain.cer",
            f"/root/.acme.sh/{{domain}}_ecc/{{domain}}.key",
        ),
        (
            f"/root/.acme.sh/{{domain}}/fullchain.cer",
            f"/root/.acme.sh/{{domain}}/{{domain}}.key",
        ),
    ]

    for cert, key in candidates:
        if not (os.path.isfile(cert) and os.path.isfile(key)):
            continue
        valid = subprocess.run(
            ["openssl", "x509", "-checkend", "86400", "-noout", "-in", cert],
            text=True,
            capture_output=True,
            check=False,
        )
        host = subprocess.run(
            ["openssl", "x509", "-checkhost", domain, "-noout", "-in", cert],
            text=True,
            capture_output=True,
            check=False,
        )
        if valid.returncode == 0 and host.returncode == 0:
            source_cert = cert
            source_key = key
            break

if source_cert and source_key:
    user_result = subprocess.run(
        ["systemctl", "show", "xray.service", "-p", "User", "--value"],
        text=True,
        capture_output=True,
        check=False,
    )
    service_user = user_result.stdout.strip() or "root"

    target_dir = Path("/usr/local/etc/xray/twinpanel-tls")
    target_dir.mkdir(parents=True, exist_ok=True)
    managed_cert = str(target_dir / "fullchain.pem")
    managed_key = str(target_dir / "privkey.pem")

    shutil.copyfile(source_cert, managed_cert)
    shutil.copyfile(source_key, managed_key)
    os.chmod(managed_cert, 0o644)
    os.chmod(managed_key, 0o600)

    if service_user != "root":
        try:
            entry = pwd.getpwnam(service_user)
            os.chown(managed_cert, entry.pw_uid, entry.pw_gid)
            os.chown(managed_key, entry.pw_uid, entry.pw_gid)
        except KeyError:
            managed_cert = ""
            managed_key = ""

    tls_enabled = bool(managed_cert and managed_key)

state = {{
    "version": 2,
    "reality_private_key": private_key,
    "reality_password": password,
    "reality_target": reality_target,
    "reality_server_name": reality_server_name,
    "short_id_xhttp": short_id_xhttp,
    "short_id_grpc": short_id_grpc,
    "xhttp_path": xhttp_path,
    "grpc_service": grpc_service,
    "ws_path": ws_path,
    "httpupgrade_path": httpupgrade_path,
    "tls_enabled": tls_enabled,
    "tls_domain": domain if tls_enabled else "",
    "source_cert": source_cert if tls_enabled else "",
    "source_key": source_key if tls_enabled else "",
    "managed_cert": managed_cert if tls_enabled else "",
    "managed_key": managed_key if tls_enabled else "",
    "service_user": service_user,
}}

state_path.parent.mkdir(parents=True, exist_ok=True)
tmp = state_path.with_suffix(".tmp")
tmp.write_text(
    json.dumps(state, ensure_ascii=False, indent=2) + "\\n",
    encoding="utf-8",
)
os.chmod(tmp, 0o600)
os.replace(tmp, state_path)
print(json.dumps(state, ensure_ascii=False, separators=(",", ":")))
'''


def _merge_clients_script() -> str:
    return r'''
import json
import os

old_path = "/usr/local/etc/xray/config.json"
new_path = "/usr/local/etc/xray/config.json.twinpanel-modern"

with open(new_path, "r", encoding="utf-8") as handle:
    new_doc = json.load(handle)

clients_by_id = {}
email_to_id = {}

if os.path.exists(old_path):
    with open(old_path, "r", encoding="utf-8") as handle:
        old_doc = json.load(handle)

    for inbound in old_doc.get("inbounds", []):
        if (
            not isinstance(inbound, dict)
            or inbound.get("protocol") != "vless"
        ):
            continue

        clients = inbound.get("settings", {}).get("clients", [])
        if not isinstance(clients, list):
            continue

        for client in clients:
            if not isinstance(client, dict):
                continue

            client_id = str(client.get("id") or "").strip()
            email = str(client.get("email") or "").strip()
            if not client_id:
                continue

            previous = clients_by_id.get(client_id)
            if (
                previous
                and str(previous.get("email") or "").strip() not in {"", email}
            ):
                raise RuntimeError("Xray duplicate UUID conflict")

            if email and email in email_to_id and email_to_id[email] != client_id:
                raise RuntimeError("Xray duplicate email conflict")

            item = {
                "id": client_id,
                "level": int(client.get("level") or 0),
            }
            if email:
                item["email"] = email

            clients_by_id[client_id] = item
            if email:
                email_to_id[email] = client_id

for inbound in new_doc.get("inbounds", []):
    if (
        not isinstance(inbound, dict)
        or inbound.get("protocol") != "vless"
    ):
        continue

    inbound.setdefault("settings", {})["clients"] = [
        dict(item)
        for item in clients_by_id.values()
    ]

with open(new_path, "w", encoding="utf-8") as handle:
    json.dump(new_doc, handle, ensure_ascii=False, indent=2)
    handle.write("\n")

print("preserved_clients=", len(clients_by_id))
'''


def _client_sync_script(client_id: str, email: str) -> str:
    return f'''
import json

path = "/usr/local/etc/xray/config.json"
with open(path, "r", encoding="utf-8") as handle:
    doc = json.load(handle)

found = 0
for inbound in doc.get("inbounds", []):
    if (
        not isinstance(inbound, dict)
        or inbound.get("protocol") != "vless"
    ):
        continue

    clients = inbound.setdefault("settings", {{}}).setdefault("clients", [])
    clients[:] = [
        item
        for item in clients
        if (
            isinstance(item, dict)
            and str(item.get("email") or "") != {email!r}
        )
    ]
    clients.append({{
        "id": {client_id!r},
        "email": {email!r},
        "level": 0,
    }})
    found += 1

if found < 3:
    raise RuntimeError("modern Xray inbounds are incomplete")

with open(path, "w", encoding="utf-8") as handle:
    json.dump(doc, handle, ensure_ascii=False, indent=2)
    handle.write("\\n")

print("updated_inbounds=", found)
'''


async def _ensure_modern_xray(
    conn,
    base_port: int,
    node: Node | None = None,
    *,
    bootstrap_done: bool = False,
) -> dict[str, Any]:
    import asyncio
    from .routers import provision

    base_port = int(base_port)

    if not bootstrap_done:
        ready = (
            await provision.cmd(
                conn,
                (
                    "if [ -x /usr/local/bin/xray ] "
                    "&& [ -s /usr/local/etc/xray/config.json ]; "
                    "then echo ready; else echo missing; fi"
                ),
                check=False,
            )
        ).strip()

        if ready != "ready":
            original = _originals.get("install_xray")
            if original is None:
                raise RuntimeError("legacy Xray installer unavailable")

            ok, error = await original(conn, base_port)
            if not ok:
                raise RuntimeError(error or "legacy Xray bootstrap failed")

    domain = (
        _clean_domain(getattr(node, "public_domain", None))
        if node is not None
        else ""
    )

    state_script = _state_generator_script(domain)
    state_b64 = base64.b64encode(state_script.encode()).decode()
    state_raw = await provision.cmd(
        conn,
        f"printf '%s' {shlex.quote(state_b64)} | base64 -d | python3",
    )

    try:
        state = json.loads(state_raw.strip().splitlines()[-1])
    except Exception as exc:
        raise RuntimeError(
            "cannot parse Xray modern state: " + repr(exc)
        ) from exc

    private_key = str(state.get("reality_private_key") or "").strip()
    if not private_key:
        raise RuntimeError("REALITY private key is empty")

    available_profiles = [PROFILE_XHTTP, PROFILE_GRPC]
    if bool(state.get("tls_enabled")):
        available_profiles.extend([PROFILE_WS, PROFILE_HTTPUPGRADE])

    candidate_ports = [base_port] + [
        _target_port(base_port, profile)
        for profile in available_profiles
    ]

    for candidate in candidate_ports:
        occupied = (
            await provision.cmd(
                conn,
                (
                    "ss -H -lntp 2>/dev/null "
                    f"| awk '$4 ~ /:{int(candidate)}$/ {{print}}' "
                    "| head -1"
                ),
                check=False,
            )
        ).strip()

        if occupied and "xray" not in occupied.lower():
            raise RuntimeError(
                "Xray modern port collision "
                f"port={candidate} listener={occupied[:300]}"
            )

    reality_common = {
        "show": False,
        "target": str(state.get("reality_target") or XRAY_REALITY_TARGET),
        "xver": 0,
        "serverNames": [
            str(
                state.get("reality_server_name")
                or XRAY_REALITY_SERVER_NAME
            )
        ],
        "privateKey": private_key,
    }

    inbounds: list[dict[str, Any]] = [
        {
            "tag": "vless-in",
            "listen": "0.0.0.0",
            "port": base_port,
            "protocol": "vless",
            "settings": {
                "clients": [],
                "decryption": "none",
            },
            "streamSettings": {
                "network": "tcp",
                "security": "none",
            },
        },
        {
            "tag": "vless-xhttp-reality",
            "listen": "0.0.0.0",
            "port": _target_port(base_port, PROFILE_XHTTP),
            "protocol": "vless",
            "settings": {
                "clients": [],
                "decryption": "none",
            },
            "streamSettings": {
                "network": "xhttp",
                "security": "reality",
                "xhttpSettings": {
                    "path": str(state["xhttp_path"]),
                    "mode": "stream-up",
                },
                "realitySettings": {
                    **reality_common,
                    "shortIds": [str(state["short_id_xhttp"])],
                },
            },
        },
        {
            "tag": "vless-grpc-reality",
            "listen": "0.0.0.0",
            "port": _target_port(base_port, PROFILE_GRPC),
            "protocol": "vless",
            "settings": {
                "clients": [],
                "decryption": "none",
            },
            "streamSettings": {
                "network": "grpc",
                "security": "reality",
                "grpcSettings": {
                    "serviceName": str(state["grpc_service"]),
                    "multiMode": False,
                },
                "realitySettings": {
                    **reality_common,
                    "shortIds": [str(state["short_id_grpc"])],
                },
            },
        },
    ]

    if PROFILE_WS in available_profiles:
        inbounds.append(
            {
                "tag": "vless-ws-tls",
                "listen": "0.0.0.0",
                "port": _target_port(base_port, PROFILE_WS),
                "protocol": "vless",
                "settings": {
                    "clients": [],
                    "decryption": "none",
                },
                "streamSettings": {
                    "network": "ws",
                    "security": "tls",
                    "wsSettings": {
                        "path": str(state["ws_path"]),
                    },
                    "tlsSettings": {
                        "serverName": str(state["tls_domain"]),
                        "minVersion": "1.2",
                        "alpn": ["http/1.1"],
                        "certificates": [
                            {
                                "certificateFile": str(state["managed_cert"]),
                                "keyFile": str(state["managed_key"]),
                            }
                        ],
                    },
                },
            }
        )

    if PROFILE_HTTPUPGRADE in available_profiles:
        inbounds.append(
            {
                "tag": "vless-httpupgrade-tls",
                "listen": "0.0.0.0",
                "port": _target_port(base_port, PROFILE_HTTPUPGRADE),
                "protocol": "vless",
                "settings": {
                    "clients": [],
                    "decryption": "none",
                },
                "streamSettings": {
                    "network": "httpupgrade",
                    "security": "tls",
                    "httpupgradeSettings": {
                        "path": str(state["httpupgrade_path"]),
                        "host": str(state["tls_domain"]),
                    },
                    "tlsSettings": {
                        "serverName": str(state["tls_domain"]),
                        "minVersion": "1.2",
                        "alpn": ["http/1.1"],
                        "certificates": [
                            {
                                "certificateFile": str(state["managed_cert"]),
                                "keyFile": str(state["managed_key"]),
                            }
                        ],
                    },
                },
            }
        )

    inbounds.append(
        {
            "tag": "api",
            "listen": "127.0.0.1",
            "port": 10085,
            "protocol": "dokodemo-door",
            "settings": {
                "address": "127.0.0.1",
            },
        }
    )

    config = {
        "log": {"loglevel": "warning"},
        "api": {
            "tag": "api",
            "services": [
                "HandlerService",
                "LoggerService",
                "StatsService",
            ],
        },
        "stats": {},
        "policy": {
            "levels": {
                "0": {
                    "statsUserUplink": True,
                    "statsUserDownlink": True,
                }
            },
            "system": {
                "statsInboundUplink": True,
                "statsInboundDownlink": True,
            },
        },
        "inbounds": inbounds,
        "outbounds": [
            {
                "protocol": "freedom",
                "tag": "direct",
            }
        ],
        "routing": {
            "rules": [
                {
                    "type": "field",
                    "inboundTag": ["api"],
                    "outboundTag": "api",
                }
            ]
        },
    }

    config_b64 = base64.b64encode(
        json.dumps(config, ensure_ascii=False).encode()
    ).decode()
    merge_b64 = base64.b64encode(_merge_clients_script().encode()).decode()

    temp_path = "/usr/local/etc/xray/config.json.twinpanel-modern"

    await provision.cmd(
        conn,
        (
            "mkdir -p /usr/local/etc/xray; "
            f"printf '%s' {shlex.quote(config_b64)} "
            f"| base64 -d > {shlex.quote(temp_path)}; "
            f"printf '%s' {shlex.quote(merge_b64)} "
            "| base64 -d | python3"
        ),
    )

    await provision.cmd(
        conn,
        (
            "/usr/local/bin/xray run -test "
            f"-config {shlex.quote(temp_path)}"
        ),
    )

    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    backup_path = (
        "/usr/local/etc/xray/"
        f"config.json.bak-modern-{stamp}"
    )

    await provision.cmd(
        conn,
        (
            "if [ -f /usr/local/etc/xray/config.json ]; "
            f"then cp -a /usr/local/etc/xray/config.json {shlex.quote(backup_path)}; "
            "fi; "
            f"install -o root -g root -m 0644 {shlex.quote(temp_path)} "
            "/usr/local/etc/xray/config.json; "
            f"rm -f {shlex.quote(temp_path)}; "
            "systemctl enable xray >/dev/null; "
            "systemctl restart xray"
        ),
    )

    await asyncio.sleep(1)

    service_ok = await provision.active(conn, "xray")
    listeners_ok = True

    for candidate in candidate_ports:
        if not await provision.listener(conn, candidate, "tcp"):
            listeners_ok = False
            break

    if not (service_ok and listeners_ok):
        await provision.cmd(
            conn,
            (
                f"if [ -f {shlex.quote(backup_path)} ]; "
                f"then cp -a {shlex.quote(backup_path)} "
                "/usr/local/etc/xray/config.json; "
                "systemctl restart xray; fi"
            ),
            check=False,
        )
        raise RuntimeError(
            "modern Xray restart/listener verification failed; "
            "previous config restored"
        )

    for candidate in candidate_ports:
        await provision.ufw_allow(conn, candidate, "tcp")

    await provision.cmd(
        conn,
        (
            "mkdir -p /etc/twinpanel/managed-identities; "
            "chmod 700 /etc/twinpanel/managed-identities; "
            "touch /etc/twinpanel/managed-identities/v2ray-modern"
        ),
    )

    state["available_profiles"] = available_profiles
    state["base_port"] = base_port
    return state


async def _install_xray_modern(conn, port: int):
    original = _originals.get("install_xray")
    if original is None:
        return False, "legacy Xray installer unavailable"

    ok, error = await original(conn, int(port))
    if not ok:
        return ok, error

    try:
        await _ensure_modern_xray(
            conn,
            int(port),
            None,
            bootstrap_done=True,
        )
        return True, None
    except Exception as exc:
        return False, str(exc)[:1800]


async def _existing_ok_modern(conn, protocol: str, settings):
    original = _originals.get("existing_ok")

    if protocol != "v2ray":
        return await original(conn, protocol, settings)

    from .routers import provision

    base_port = int(settings.xray_port)
    if not await provision.active(conn, "xray"):
        return False

    for candidate in (
        base_port,
        _target_port(base_port, PROFILE_XHTTP),
        _target_port(base_port, PROFILE_GRPC),
    ):
        if not await provision.listener(conn, candidate, "tcp"):
            return False

    return True


def _existing_uuid(item: dict[str, Any] | None) -> str:
    if not isinstance(item, dict):
        return ""

    value = str(item.get("uuid") or "").strip()
    if value:
        return value

    uri = str(item.get("uri") or "").strip()
    match = re.match(r"^vless://([^@/?#]+)@", uri)
    return match.group(1) if match else ""


async def _xray_account_modern(
    db: Session,
    node: Node,
    sub: Subscription,
    user: User,
    client_id: str,
) -> dict[str, Any]:
    from .routers import account_delivery, provision

    conn = await account_delivery.ssh_connect_saved(node, db)

    try:
        base_port = account_delivery._port(db, node.id, "v2ray")
        state = await _ensure_modern_xray(conn, base_port, node)

        email = f"mv-{sub.id}@twinpanel"
        sync_script = _client_sync_script(client_id, email)
        sync_b64 = base64.b64encode(sync_script.encode()).decode()

        await provision.cmd(
            conn,
            f"printf '%s' {shlex.quote(sync_b64)} | base64 -d | python3",
        )
        await provision.cmd(
            conn,
            (
                "/usr/local/bin/xray run -test "
                "-config /usr/local/etc/xray/config.json"
            ),
        )
        await provision.cmd(conn, "systemctl restart xray")

        if not await provision.active(conn, "xray"):
            raise RuntimeError("Xray service did not remain active")

        username_part = account_delivery._download_filename_part(
            sub.account_username
            or account_delivery._safe_username(sub, user),
            f"user{sub.id}",
        )
        country_part = account_delivery._country_download_name(node)
        profile_name = f"{username_part}-{country_part}"

        available = set(state.get("available_profiles") or [])
        order: list[str] = []

        if PROFILE_WS in available:
            order.append(PROFILE_WS)
        order.append(PROFILE_XHTTP)
        if PROFILE_HTTPUPGRADE in available:
            order.append(PROFILE_HTTPUPGRADE)
        order.append(PROFILE_GRPC)

        profiles = []
        for profile in order:
            if profile not in available:
                continue

            host, public_port = _profile_endpoint(db, node, profile)
            uri = _build_uri(
                profile=profile,
                client_id=client_id,
                host=host,
                port=public_port,
                profile_name=profile_name,
                state=state,
            )
            meta = PROFILE_META[profile]

            profiles.append(
                {
                    "id": profile,
                    "title": meta["title"],
                    "recommended": bool(meta["recommended"]),
                    "security": meta["security"],
                    "transport": meta["transport"],
                    "server": host,
                    "port": public_port,
                    "uri": uri,
                    "sni": (
                        state.get("tls_domain")
                        if profile in _TLS_PROFILES
                        else state.get("reality_server_name")
                    ),
                }
            )

        if not profiles:
            raise RuntimeError("no modern Xray profile is available")

        primary = profiles[0]
        return {
            "node_id": node.id,
            "node": node.name,
            "server": primary["server"],
            "server_ip": primary["server"],
            "port": primary["port"],
            "uuid": client_id,
            "profile": primary["id"],
            "security": primary["security"],
            "transport": primary["transport"],
            "uri": primary["uri"],
            "profiles": profiles,
            "tls_available": bool(state.get("tls_enabled")),
            "legacy_plain_preserved": True,
        }

    finally:
        conn.close()
        await conn.wait_closed()


def _live_client_item_modern(
    db: Session,
    sub: Subscription,
    protocol: str,
    item: dict[str, Any],
) -> dict[str, Any]:
    original = _originals["live_client_item"]
    result = original(db, sub, protocol, item)

    if (
        str(protocol or "").strip().lower() != "v2ray"
        or not isinstance(result, dict)
    ):
        return result

    profiles = result.get("profiles")
    if not isinstance(profiles, list):
        return result

    try:
        node_id = int(result.get("node_id"))
    except (TypeError, ValueError):
        return result

    node = db.get(Node, node_id)
    if not node or node.node_type != NodeType.EXIT:
        return result

    updated = []
    for raw in profiles:
        if not isinstance(raw, dict):
            continue

        profile = dict(raw)
        profile_id = str(profile.get("id") or "").strip()
        if profile_id not in PROFILE_META:
            updated.append(profile)
            continue

        host, port = _profile_endpoint(db, node, profile_id)
        profile["server"] = host
        profile["port"] = port

        uri = str(profile.get("uri") or "")
        if uri:
            profile["uri"] = re.sub(
                r"^(vless://[^@]+@)[^:/?#]+:\d+",
                rf"\g<1>{host}:{port}",
                uri,
                count=1,
            )

        updated.append(profile)

    if updated:
        result["profiles"] = updated
        primary = updated[0]
        result["server"] = primary.get("server")
        result["server_ip"] = primary.get("server")
        result["port"] = primary.get("port")
        if primary.get("uri"):
            result["uri"] = primary["uri"]

    return result


def _public_payload_modern(
    db: Session,
    sub: Subscription,
) -> dict[str, Any]:
    payload = _originals["public_payload"](db, sub)
    from .routers import account_delivery

    for credential in payload.get("credentials", []):
        if str(credential.get("protocol") or "").strip().lower() != "v2ray":
            continue

        items = credential.get("items")
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict):
                continue
            profiles = item.get("profiles")
            if not isinstance(profiles, list):
                continue

            for profile in profiles:
                if isinstance(profile, dict) and profile.get("uri"):
                    profile["qr"] = account_delivery._qr_data_uri(
                        str(profile["uri"])
                    )

    return payload


def _service_routes_modern(
    db: Session,
    exit_node: Node,
    exit_tunnel_ip: str,
) -> list[dict]:
    routes = list(
        _originals["service_routes"](
            db,
            exit_node,
            exit_tunnel_ip,
        )
    )

    cfg = (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == exit_node.id,
            NodeProtocolConfig.protocol == "v2ray",
        )
        .first()
    )

    if not cfg or _enum_value(cfg.status) != "online":
        return routes

    base_port = int(cfg.port or 8443)
    existing = {
        (
            str(route.get("protocol") or ""),
            int(route.get("public_port") or 0),
        )
        for route in routes
        if isinstance(route, dict)
    }

    for profile in (
        PROFILE_XHTTP,
        PROFILE_GRPC,
        PROFILE_WS,
        PROFILE_HTTPUPGRADE,
    ):
        public_port = _public_port(exit_node.id, profile)
        key = ("v2ray", public_port)
        if key in existing:
            continue

        routes.append(
            {
                "protocol": "v2ray",
                "profile": profile,
                "exit_node_id": int(exit_node.id),
                "public_port": public_port,
                "target_ip": exit_tunnel_ip,
                "target_port": _target_port(base_port, profile),
                "transport": "tcp",
                "client_subnet": None,
            }
        )

    return routes


def _modern_item_present(item: dict[str, Any]) -> bool:
    profiles = item.get("profiles")
    if not isinstance(profiles, list):
        return False

    ids = {
        str(profile.get("id") or "")
        for profile in profiles
        if isinstance(profile, dict)
    }
    return PROFILE_XHTTP in ids


def _normalize_items(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [
            dict(item)
            for item in raw
            if isinstance(item, dict)
        ]
    if isinstance(raw, dict):
        return [dict(raw)]
    return []


async def _ensure_subscription_modern(
    db: Session,
    sub: Subscription,
    *,
    force: bool = False,
) -> dict[str, Any]:
    from .routers import account_delivery

    selected_protocols = {
        str(row[0]).strip().lower()
        for row in (
            db.query(SubscriptionProtocol.protocol)
            .filter(SubscriptionProtocol.subscription_id == sub.id)
            .all()
        )
    }

    if "v2ray" not in selected_protocols:
        return {
            "ok": True,
            "skipped": True,
            "reason": "v2ray_not_selected",
            "connection": account_delivery._stored_info(db, sub),
        }

    cred = (
        db.query(ProtocolCredential)
        .filter(
            ProtocolCredential.subscription_id == sub.id,
            ProtocolCredential.protocol == "v2ray",
        )
        .first()
    )

    existing_items = _normalize_items(
        account_delivery._dec(cred.config_text_encrypted)
        if cred
        else None
    )

    user = db.get(User, sub.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")

    nodes = []
    for node in (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.node_type == NodeType.EXIT,
        )
        .order_by(Node.id.asc())
        .all()
    ):
        if not bool(getattr(node, "enable_v2ray", False)):
            continue

        cfg = (
            db.query(NodeProtocolConfig)
            .filter(
                NodeProtocolConfig.node_id == node.id,
                NodeProtocolConfig.protocol == "v2ray",
            )
            .first()
        )
        if not cfg or _enum_value(cfg.status) != "online":
            continue
        nodes.append(node)

    if not nodes:
        raise HTTPException(
            status_code=409,
            detail="هیچ سرور خروجی Xray آنلاین برای این اشتراک وجود ندارد",
        )

    old_by_node: dict[int, dict[str, Any]] = {}
    for item in existing_items:
        try:
            item_node_id = int(item.get("node_id"))
        except (TypeError, ValueError):
            continue
        old_by_node[item_node_id] = item

    eligible_ids = {int(node.id) for node in nodes}
    modern_ids = {
        node_id
        for node_id, item in old_by_node.items()
        if _modern_item_present(item)
    }

    if not force and eligible_ids and eligible_ids <= modern_ids:
        return {
            "ok": True,
            "skipped": True,
            "reason": "already_modern",
            "connection": account_delivery._stored_info(db, sub),
        }

    final_by_node = dict(old_by_node)
    migrated = []
    errors = []

    for node in nodes:
        if (
            not force
            and int(node.id) in modern_ids
        ):
            continue

        previous = old_by_node.get(int(node.id))
        client_id = _existing_uuid(previous) or str(uuid.uuid4())

        try:
            item = await _xray_account_modern(
                db,
                node,
                sub,
                user,
                client_id,
            )
            final_by_node[int(node.id)] = item
            migrated.append(int(node.id))
        except Exception as exc:
            errors.append(
                {
                    "node_id": int(node.id),
                    "node": node.name,
                    "error": str(exc)[:1200],
                }
            )

    if (
        not migrated
        and not any(
            _modern_item_present(item)
            for item in final_by_node.values()
        )
    ):
        raise HTTPException(
            status_code=502,
            detail={
                "message": "ساخت اتصال‌های جدید Xray ناموفق بود",
                "errors": errors,
            },
        )

    if not cred:
        cred = ProtocolCredential(
            subscription_id=sub.id,
            protocol="v2ray",
        )
        db.add(cred)

    ordered = [
        final_by_node[key]
        for key in sorted(final_by_node)
        if isinstance(final_by_node[key], dict)
    ]

    cred.config_text_encrypted = account_delivery._enc(ordered)
    cred.is_active = True
    db.commit()

    return {
        "ok": len(errors) == 0,
        "migrated_node_ids": migrated,
        "errors": errors,
        "connection": account_delivery._stored_info(db, sub),
    }


@router.post("/customer/{subscription_id}/ensure")
async def customer_ensure_modern_xray(
    subscription_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sub = db.get(Subscription, subscription_id)

    if not sub or int(sub.user_id) != int(user.id):
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")

    if _enum_value(sub.status) != "active":
        raise HTTPException(status_code=403, detail="اشتراک فعال نیست")

    if sub.expires_at and sub.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=403, detail="اشتراک منقضی شده است")

    return await _ensure_subscription_modern(db, sub, force=False)


@router.post(
    "/admin/{subscription_id}/ensure",
    dependencies=[Depends(require_admin)],
)
async def admin_ensure_modern_xray(
    subscription_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
):
    sub = db.get(Subscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")
    return await _ensure_subscription_modern(db, sub, force=bool(force))


def apply_xray_modern_runtime() -> None:
    global _runtime_applied

    if _runtime_applied:
        return

    from .routers import account_delivery, provision, tunnels

    _originals["install_xray"] = provision.install_xray
    _originals["existing_ok"] = provision.existing_ok
    _originals["xray_account"] = account_delivery._xray
    _originals["live_client_item"] = account_delivery._live_client_item
    _originals["public_payload"] = account_delivery._public_payload
    _originals["service_routes"] = tunnels._service_routes_for_exit

    provision.install_xray = _install_xray_modern
    provision.existing_ok = _existing_ok_modern
    account_delivery._xray = _xray_account_modern
    account_delivery._live_client_item = _live_client_item_modern
    account_delivery._public_payload = _public_payload_modern
    tunnels._service_routes_for_exit = _service_routes_modern

    _runtime_applied = True

    print(
        "TWINPANEL_XRAY_MODERN_RUNTIME_V2_ACTIVE "
        "profiles=websocket_tls,xhttp_reality,httpupgrade_tls,grpc_reality "
        "legacy_plain_preserved=1 transport_ui_hidden=1",
        flush=True,
    )
