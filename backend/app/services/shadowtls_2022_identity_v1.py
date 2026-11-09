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
    except Exception as exc:
        raise ValueError("shadowtls_2022_key_invalid") from exc
    if len(raw) != 16:
        raise ValueError("shadowtls_2022_key_length_invalid")
    return value


def user_inner_key(username: str, outer_password: str, derivation_secret: str) -> str:
    """Strong 16-byte SS2022 user key, even for migrated short outer passwords.

    A private 32-byte node-specific seed (never included in client profiles)
    keys HMAC. The user's historical ShadowTLS password and exact name are
    inputs, but knowing a short outer password and the shared SS2022 server
    key is insufficient to derive another user's inner credential.
    """
    if not isinstance(username, str) or not username.strip() or username != username.strip():
        raise ValueError("shadowtls_2022_username_invalid")
    if len(username.encode("utf-8")) > 160 or username.startswith(("twinpanel-bootstrap", "__twinpanel_revoked__")):
        raise ValueError("shadowtls_2022_username_invalid")
    if not isinstance(outer_password, str) or not outer_password:
        raise ValueError("shadowtls_2022_outer_secret_invalid")
    try:
        seed = base64.b64decode(derivation_secret, validate=True)
    except Exception as exc:
        raise ValueError("shadowtls_2022_derivation_secret_invalid") from exc
    if len(seed) < 32:
        raise ValueError("shadowtls_2022_derivation_secret_invalid")
    derived = hmac.new(
        seed,
        _DOMAIN + username.encode("utf-8") + b"\0" + outer_password.encode("utf-8"),
        hashlib.sha256,
    ).digest()[:16]
    return base64.b64encode(derived).decode("ascii")


def stage_parallel_identity_inbounds(
    config: dict[str, Any],
    *,
    listen_port: int,
    server_key: str,
    derivation_secret: str,
) -> dict[str, Any]:
    """Build an additive (non-installed) modern ShadowTLS protocol snapshot.

    Reuses real legacy authenticated ShadowTLS users while preserving every
    existing inbound byte-for-byte in the output. Does not migrate revoked
    users, silently overwrite another inbound, or auto-publish a new port.
    """
    _validate_key(server_key)
    # Validate the private seed before constructing or publishing any user key.
    user_inner_key("migration-preflight", "check", derivation_secret)
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
        # Same port on any address family is unsafe for additive rollout.
        # Refuse even loopback duplicates; node provisioning must reserve a
        # genuinely separate port and verify all tunnel listeners as well.
        if existing.get("listen_port") == listen_port:
            raise ValueError("shadowtls_2022_port_conflict")
    real_users = []
    seen = set()
    for entry in legacy[0].get("users") or []:
        if not isinstance(entry, dict):
            continue
        username = str(entry.get("name") or "")
        password = str(entry.get("password") or "")
        if username.startswith(("twinpanel-bootstrap", "__twinpanel_revoked__")):
            continue  # bootstrap/revocation sentinels are never routable
        if not username or not password:
            raise ValueError("shadowtls_2022_legacy_identity_invalid")
        if username in seen:
            raise ValueError("shadowtls_2022_duplicate_user")
        seen.add(username)
        real_users.append({
            "name": username,
            "password": user_inner_key(username, password, derivation_secret),
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
    user_key: str,
    listen_port: int,
    server_key: str,
) -> list[dict[str, Any]]:
    """Return a standalone client transport + per-user authenticated proxy.

    Call only after the matching parallel listener is installed, its tunnel
    is configured, and a real end-to-end client handshake has succeeded.
    """
    _validate_key(server_key)
    _validate_key(user_key)
    if not isinstance(username, str) or not username.strip():
        raise ValueError("shadowtls_2022_username_invalid")
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


def parallel_user_sync_script() -> str:
    """Python fragment embedded in each existing node account mutation.

    Safe no-op until the parallel listener has been deliberately installed.
    When it exists, update/revoke matching users on *both* the outer and
    authenticated inner in one atomic sing-box config rewrite.
    """
    return '''
# Optional ShadowTLS 2022 synchronization; legacy-only nodes are untouched.
import base64 as _st_base64
import hashlib as _st_hashlib
import hmac as _st_hmac
_st_outer = next((x for x in inbounds if isinstance(x,dict) and
    x.get("tag")=="twinpanel-shadowtls-identity-in"),None)
_st_inner = next((x for x in inbounds if isinstance(x,dict) and
    x.get("tag")=="twinpanel-shadowtls-identity-inner"),None)
if _st_outer is not None or _st_inner is not None:
    if not (isinstance(_st_outer,dict) and isinstance(_st_inner,dict)
            and _st_outer.get("type")=="shadowtls"
            and _st_inner.get("type")=="shadowsocks"
            and _st_inner.get("method")=="2022-blake3-aes-128-gcm"):
        raise SystemExit("shadowtls_identity_parallel_incomplete")
    _st_key = _st_inner.get("password")
    _st_state_path = STATE
    _st_state = json.load(open(_st_state_path,encoding="utf-8"))
    _st_opts = _st_state.get("shadowtls_identity2022") if isinstance(_st_state,dict) else None
    _st_secret = (_st_opts or {}).get("derivation_secret")
    try:
        if len(_st_base64.b64decode(_st_secret,validate=True))<32:
            raise ValueError("private seed length")
    except Exception:
        raise SystemExit("shadowtls_identity_derivation_secret_invalid")
    try:
        if len(_st_base64.b64decode(_st_key,validate=True))!=16:
            raise ValueError("key length")
    except Exception:
        raise SystemExit("shadowtls_identity_server_key_invalid")
    _st_legacy = next((x for x in inbounds if isinstance(x,dict) and
        x.get("tag")=="twinpanel-shadowtls-in" and
        x.get("type")=="shadowtls"),None)
    if not isinstance(_st_legacy,dict):
        raise SystemExit("shadowtls_identity_legacy_outer_missing")
    _st_synced_users=[]
    _st_inner_users=[]
    _st_seen=set()
    for _st_row in _st_legacy.get("users") or []:
        if not isinstance(_st_row,dict):
            continue
        _st_username=str(_st_row.get("name") or "")
        _st_password=str(_st_row.get("password") or "")
        if _st_username.startswith(("twinpanel-bootstrap","__twinpanel_revoked__")):
            continue
        if _st_username in _st_seen or not _st_username or not _st_password:
            raise SystemExit("shadowtls_identity_duplicate_or_invalid")
        _st_seen.add(_st_username)
        _st_synced_users.append(dict(_st_row))
        _st_inner_users.append(dict(
            name=_st_username,
            password=_st_base64.b64encode(_st_hmac.new(
                _st_base64.b64decode(_st_secret,validate=True),
                b"twinpanel:shadowtls:identity-inner:2022:v1:"+
                    _st_username.encode("utf-8")+b"\\x00"+_st_password.encode("utf-8"),
                _st_hashlib.sha256,
            ).digest()[:16]).decode("ascii"),
        ))
    if not _st_inner_users:
        # A random, undisclosed sentinel avoids leaving the parallel
        # server in single-user/unauthenticated fallback after last revoke.
        _st_inner_users=[dict(
            name="twinpanel-identity-disabled",
            password=_st_base64.b64encode(_st_hmac.new(
                _st_key.encode("utf-8"),b"twinpanel-disabled-inner",
                _st_hashlib.sha256,
            ).digest()[:16]).decode("ascii"),
        )]
    _st_outer["users"] = _st_synced_users or [
        dict(name="twinpanel-identity-disabled",
             password=_st_base64.b64encode(_st_hmac.new(
                 _st_key.encode("utf-8"),b"twinpanel-disabled-outer",
                 _st_hashlib.sha256,
             ).digest()[:16]).decode("ascii"))
    ]
    _st_inner["users"] = _st_inner_users
'''
