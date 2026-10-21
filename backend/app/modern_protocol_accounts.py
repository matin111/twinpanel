from __future__ import annotations

import base64
import json
import secrets
import shlex
import uuid
from dataclasses import dataclass
from typing import Any

from .modern_protocol_runtime import CONFIG_PATH, MODERN_PROTOCOL_SPECS, SERVICE_NAME
from .routers.provision import cmd

MODERN_ACCOUNT_PROTOCOLS = ("hysteria2", "tuic", "anytls")


@dataclass(frozen=True)
class ModernAccountSecret:
    protocol: str
    username: str
    password: str
    uuid: str | None = None


def account_username(subscription_id: int) -> str:
    value = int(subscription_id)
    if value <= 0:
        raise ValueError("subscription_id must be positive")
    return f"tp-sub-{value}"


def new_account_secret(protocol: str, subscription_id: int) -> ModernAccountSecret:
    protocol = str(protocol or "").strip().lower()
    if protocol not in MODERN_ACCOUNT_PROTOCOLS:
        raise ValueError(f"unsupported modern account protocol: {protocol}")
    password = secrets.token_urlsafe(32)
    return ModernAccountSecret(
        protocol=protocol,
        username=account_username(subscription_id),
        password=password,
        uuid=(str(uuid.uuid4()) if protocol == "tuic" else None),
    )


def secret_to_dict(secret: ModernAccountSecret) -> dict[str, str]:
    result = {"username": secret.username, "password": secret.password}
    if secret.uuid:
        result["uuid"] = secret.uuid
    return result


def secret_from_dict(protocol: str, subscription_id: int, value: dict[str, Any]) -> ModernAccountSecret:
    protocol = str(protocol or "").strip().lower()
    if protocol not in MODERN_ACCOUNT_PROTOCOLS:
        raise ValueError(f"unsupported modern account protocol: {protocol}")
    password = str((value or {}).get("password") or "").strip()
    if not password:
        raise ValueError("modern account password is missing")
    user_uuid = None
    if protocol == "tuic":
        user_uuid = str((value or {}).get("uuid") or "").strip()
        uuid.UUID(user_uuid)
    return ModernAccountSecret(
        protocol=protocol,
        username=account_username(subscription_id),
        password=password,
        uuid=user_uuid,
    )


def _remote_user(secret: ModernAccountSecret) -> dict[str, str]:
    if secret.protocol == "tuic":
        if not secret.uuid:
            raise ValueError("TUIC UUID is required")
        return {"name": secret.username, "uuid": secret.uuid, "password": secret.password}
    return {"name": secret.username, "password": secret.password}


def _mutation_script(protocol: str, user: dict[str, str] | None, username: str) -> str:
    spec = MODERN_PROTOCOL_SPECS[protocol]
    return f'''import json\np={CONFIG_PATH!r}\ntag={spec.tag!r}\nusername={username!r}\nuser={user!r}\nwith open(p, "r", encoding="utf-8") as h:\n    doc=json.load(h)\ninbound=next((x for x in doc.get("inbounds", []) if isinstance(x, dict) and x.get("tag")==tag), None)\nif inbound is None:\n    raise SystemExit("managed inbound not found")\nusers=inbound.get("users")\nif not isinstance(users, list):\n    users=[]\nusers=[x for x in users if not (isinstance(x, dict) and x.get("name")==username)]\nif user is not None:\n    users.append(user)\ninbound["users"]=users\nwith open(p+".new", "w", encoding="utf-8") as h:\n    json.dump(doc, h, ensure_ascii=False, indent=2)\n    h.write("\\n")\n'''


async def apply_account(conn, secret: ModernAccountSecret) -> dict[str, Any]:
    if secret.protocol not in MODERN_ACCOUNT_PROTOCOLS:
        raise ValueError(f"unsupported modern account protocol: {secret.protocol}")
    encoded = base64.b64encode(
        _mutation_script(secret.protocol, _remote_user(secret), secret.username).encode()
    ).decode()
    await cmd(
        conn,
        f"printf '%s' {shlex.quote(encoded)} | base64 -d | python3 && "
        f"/usr/local/bin/twinpanel-sing-box check -c {shlex.quote(CONFIG_PATH + '.new')} && "
        f"cp -a {shlex.quote(CONFIG_PATH)} {shlex.quote(CONFIG_PATH)}.bak-account-$(date +%Y%m%d-%H%M%S) && "
        f"mv {shlex.quote(CONFIG_PATH + '.new')} {shlex.quote(CONFIG_PATH)} && "
        f"systemctl restart {SERVICE_NAME}.service && "
        f"systemctl is-active --quiet {SERVICE_NAME}.service",
        timeout=120,
    )
    return {"ok": True, "protocol": secret.protocol, "username": secret.username}


async def remove_account(conn, protocol: str, subscription_id: int) -> dict[str, Any]:
    protocol = str(protocol or "").strip().lower()
    if protocol not in MODERN_ACCOUNT_PROTOCOLS:
        raise ValueError(f"unsupported modern account protocol: {protocol}")
    username = account_username(subscription_id)
    encoded = base64.b64encode(_mutation_script(protocol, None, username).encode()).decode()
    await cmd(
        conn,
        f"printf '%s' {shlex.quote(encoded)} | base64 -d | python3 && "
        f"/usr/local/bin/twinpanel-sing-box check -c {shlex.quote(CONFIG_PATH + '.new')} && "
        f"cp -a {shlex.quote(CONFIG_PATH)} {shlex.quote(CONFIG_PATH)}.bak-account-$(date +%Y%m%d-%H%M%S) && "
        f"mv {shlex.quote(CONFIG_PATH + '.new')} {shlex.quote(CONFIG_PATH)} && "
        f"systemctl restart {SERVICE_NAME}.service && "
        f"systemctl is-active --quiet {SERVICE_NAME}.service",
        timeout=120,
    )
    return {"ok": True, "protocol": protocol, "username": username, "removed": True}


def client_outbound(
    secret: ModernAccountSecret,
    *,
    server: str,
    port: int,
    server_name: str | None = None,
    certificate_public_key_sha256: str | None = None,
) -> dict[str, Any]:
    host = str(server or "").strip()
    if not host:
        raise ValueError("server is required")
    listen_port = int(port)
    if not 1 <= listen_port <= 65535:
        raise ValueError("invalid server port")
    tls: dict[str, Any] = {"enabled": True}
    if server_name:
        tls["server_name"] = str(server_name)
    if certificate_public_key_sha256:
        tls["certificate_public_key_sha256"] = [str(certificate_public_key_sha256)]
    outbound: dict[str, Any] = {
        "type": secret.protocol,
        "tag": f"twinpanel-{secret.protocol}",
        "server": host,
        "server_port": listen_port,
        "tls": tls,
    }
    if secret.protocol == "tuic":
        outbound.update({
            "uuid": secret.uuid,
            "password": secret.password,
            "congestion_control": "cubic",
            "zero_rtt_handshake": False,
        })
    else:
        outbound["password"] = secret.password
    return outbound


def client_profile(
    secret: ModernAccountSecret,
    *,
    server: str,
    port: int,
    server_name: str | None = None,
    certificate_public_key_sha256: str | None = None,
) -> dict[str, Any]:
    return {
        "log": {"level": "warn"},
        "inbounds": [{
            "type": "mixed",
            "tag": "mixed-in",
            "listen": "127.0.0.1",
            "listen_port": 2080,
        }],
        "outbounds": [client_outbound(
            secret,
            server=server,
            port=port,
            server_name=server_name,
            certificate_public_key_sha256=certificate_public_key_sha256,
        )],
        "route": {"final": f"twinpanel-{secret.protocol}"},
    }
