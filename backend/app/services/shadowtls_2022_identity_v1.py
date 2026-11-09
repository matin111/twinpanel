"""ShadowTLS v3 -> identity-preserving Shadowsocks 2022 migration primitives.

These PURE functions stage a parallel protocol family. They never edit a
running node, write persistent secrets, restart sing-box, change a port
binding, or modify a customer credential.

Why parallel? The legacy ShadowTLS v3 listener detours to a shared
aes-256-gcm Shadowsocks password. Switching that live inner listener to
Shadowsocks 2022 would instantly invalidate existing customer configs.
Deploying the staged listener requires a separate available public/tunnel
port, authoritative node secrets, and an explicitly coordinated migration.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
from typing import Any


LEGACY_OUTER_TAG = "twinpanel-shadowtls-in"
NEW_OUTER_TAG = "twinpanel-shadowtls-identity-in"
NEW_INNER_TAG = "twinpanel-shadowtls-identity-inner"
INNER_METHOD = "2022-blake3-aes-128-gcm"
_DOMAIN = b"twinpanel:shadowtls:identity-inner:2022:v1:"


def _validate_key(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("shadowtls_2022_key_invalid")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, Exception) as exc:
        raise ValueError("shadowtls_2022_key_invalid") from exc
    if len(raw) != 16:
        raise ValueError("shadowtls_2022_key_length_invalid")
    return value


def user_inner_key(username: str, outer_password: str) -> str:
    """Derive 16-byte SS2022 user key from the existing *private* credential.

    This function cannot be used to identify a customer without the original
    authenticated ShadowTLS secret. No IP address, shared inner password,
    plan metadata or other customer's key may be used as an identity.
    """
    if not isinstance(username, str) or not username.startswith("tp-sub-"):
        raise ValueError("shadowtls_2022_canonical_username_required")
    if not username[7:].isdigit() or int(username[7:]) <= 0:
        raise ValueError("shadowtls_2022_canonical_username_required")
    if not isinstance(outer_password, str) or len(outer_password) < 16:
        raise ValueError("shadowtls_2022_outer_secret_invalid")
    derived = hmac.new(
        outer_password.encode("utf-8"),
        _DOMAIN + username.encode("utf-8"),
        hashlib.sha256,
    ).digest()[:16]
    return base64.b64encode(derived).decode("ascii")


def stage_parallel_identity_inbounds(
    config: dict[str, Any],
    *,
    listen_port: int,
    server_key: str,
) -> dict[str, Any]:
    """Build an additive (non-installed) modern ShadowTLS protocol snapshot.

    Reuses real legacy authenticated ShadowTLS users while preserving every
    existing inbound byte-for-byte in the output. Does not migrate revoked
    users, silently overwrite another inbound, or auto-publish a new port.
    """
    _validate_key(server_key)
    if not isinstance(listen_port, int) or not 1024 <= listen_port <= 65535:
        raise ValueError("shadowtls_2022_port_invalid")
    staged = copy.deepcopy(config)
    inbounds = staged.get("inbounds")
    if not isinstance(inbounds, list):
        raise ValueError("shadowtls_2022_inbounds_missing")
    legacy = [x for x in inbounds if isinstance(x, dict)
              and x.get("tag") == LEGACY_OUTER_TAG
              and x.get("type") == "shadowtls"]
    if len(legacy) != 1 or int(legacy[0].get("version") or 0) != 3:
        raise ValueError("shadowtls_2022_legacy_outer_missing")
    for existing in inbounds:
        if not isinstance(existing, dict):
            continue
        if existing.get("tag") in (NEW_OUTER_TAG, NEW_INNER_TAG):
            raise ValueError("shadowtls_2022_parallel_tag_already_exists")
        if existing.get("listen_port") == listen_port and existing.get("listen") not in ("127.0.0.1", "::1"):
            raise ValueError("shadowtls_2022_port_conflict")
    real_users = []
    seen = set()
    for entry in legacy[0].get("users") or []:
        if not isinstance(entry, dict):
            continue
        username = str(entry.get("name") or "")
        password = str(entry.get("password") or "")
        if not username.startswith("tp-sub-"):
            continue  # bootstrap/revocation sentinels are never routable
        if username in seen:
            raise ValueError("shadowtls_2022_duplicate_user")
        seen.add(username)
        real_users.append({
            "name": username,
            "password": user_inner_key(username, password),
        })
    if not real_users:
        raise ValueError("shadowtls_2022_no_verified_users")
    modern_outer = copy.deepcopy(legacy[0])
    modern_outer["tag"] = NEW_OUTER_TAG
    modern_outer["listen_port"] = listen_port
    modern_outer["detour"] = NEW_INNER_TAG
    modern_inner = {
        "type": "shadowsocks",
        "tag": NEW_INNER_TAG,
        "listen": "127.0.0.1",
        "method": INNER_METHOD,
        "password": server_key,
        "users": real_users,
    }
    inbounds.extend([modern_outer, modern_inner])
    return staged


def identity_client_outbounds(
    legacy_transport: dict[str, Any],
    *,
    username: str,
    outer_password: str,
    listen_port: int,
    server_key: str,
) -> list[dict[str, Any]]:
    """Return a standalone client transport + per-user authenticated proxy.

    Call only after the matching parallel listener is installed, its tunnel
    is configured, and a real end-to-end client handshake has succeeded.
    """
    _validate_key(server_key)
    user_key = user_inner_key(username, outer_password)
    if not 1024 <= listen_port <= 65535:
        raise ValueError("shadowtls_2022_port_invalid")
    if legacy_transport.get("type") != "shadowtls":
        raise ValueError("shadowtls_2022_transport_invalid")
    transport = copy.deepcopy(legacy_transport)
    transport["tag"] = "twinpanel-shadowtls-identity-transport"
    transport["server_port"] = listen_port
    proxy = {
        "type": "shadowsocks",
        "tag": "twinpanel-shadowtls-identity",
        "method": INNER_METHOD,
        "password": server_key + ":" + user_key,
        "detour": transport["tag"],
        "udp_over_tcp": {"enabled": True, "version": 2},
    }
    return [proxy, transport]
