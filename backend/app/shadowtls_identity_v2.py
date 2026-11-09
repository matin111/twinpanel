"""Identity-preserving ShadowTLS v3 migration without breaking legacy links.

The original shared AEAD Shadowsocks detour stays intact. A separate
ShadowTLS listener and Shadowsocks 2022 multi-user inbound provide exact,
authenticated username attribution for new generated connection profiles.
The node receives no customer-facing database secrets beyond the existing
ShadowTLS v3 user passwords already installed there.

IMPORTANT: This module supplies staged provisioning primitives. It does not
claim legacy links can be attributed, and it must not be enabled until
per-node TCP reachability and end-to-end collector tests pass.
"""
from __future__ import annotations

import base64
import hashlib
import hmac

IDENTIFIED_INBOUND_TAG = "twinpanel-shadowtls-identified-in"
IDENTIFIED_INNER_TAG = "twinpanel-shadowtls-identified-inner"
IDENTIFIED_METHOD = "2022-blake3-aes-128-gcm"
IDENTIFIED_PORT_OFFSET = 10000


def identified_user_key(server_key: str, username: str, shadowtls_password: str) -> str:
    """Generate a cryptographic per-subscriber 16-byte Shadowsocks 2022 key."""
    raw = base64.b64decode(server_key, validate=True)
    if len(raw) != 16 or not username or not shadowtls_password:
        raise ValueError("invalid_shadowtls_identified_key_material")
    data = username.encode("utf-8") + bytes([0]) + shadowtls_password.encode("utf-8")
    return base64.b64encode(hmac.new(raw, data, hashlib.sha256).digest()[:16]).decode("ascii")


# Pure node-local Python; embedded into existing authenticated node mutation
# scripts, which have access to config, node state, and installed outer users.
NODE_HELPER_SCRIPT = """
import base64 as _shadow_b64
import copy as _shadow_copy
import hashlib as _shadow_hash
import hmac as _shadow_hmac
import secrets as _shadow_secrets

def ensure_identified_shadowtls(inbounds, state, legacy_tag, legacy_inner_tag):
    outer = next((row for row in inbounds
                  if isinstance(row, dict) and row.get("tag") == legacy_tag
                  and row.get("type") == "shadowtls"), None)
    inner = next((row for row in inbounds
                  if isinstance(row, dict) and row.get("tag") == legacy_inner_tag
                  and row.get("type") == "shadowsocks"), None)
    if not isinstance(outer, dict) or not isinstance(inner, dict):
        raise ValueError("legacy_shadowtls_inbounds_unavailable")
    if inner.get("method") != "aes-256-gcm":
        raise ValueError("legacy_shadowtls_method_changed")
    original_port = int(outer.get("listen_port") or 0)
    identified_port = original_port + 10000
    if original_port < 1 or identified_port > 65535:
        raise ValueError("shadowtls_identified_port_unavailable")

    outer_users = outer.get("users")
    if not isinstance(outer_users, list):
        raise ValueError("shadowtls_user_catalog_unavailable")
    users = []
    names = set()
    for item in outer_users:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        password = str(item.get("password") or "")
        if not name or name.startswith("__twinpanel_revoked__"):
            continue
        if not password or name in names:
            raise ValueError("shadowtls_user_catalog_duplicate_or_incomplete")
        names.add(name)
        users.append((name, password))

    state_entry = state.setdefault("shadowtls", {})
    if not isinstance(state_entry, dict):
        raise ValueError("shadowtls_node_state_invalid")
    server_key = state_entry.get("identified_server_key")
    if not server_key:
        server_key = _shadow_b64.b64encode(_shadow_secrets.token_bytes(16)).decode("ascii")
        state_entry["identified_server_key"] = server_key
    raw = _shadow_b64.b64decode(server_key, validate=True)
    if len(raw) != 16:
        raise ValueError("shadowtls_identified_server_key_invalid")

    identified_inner_tag = "twinpanel-shadowtls-identified-inner"
    identified_tag = "twinpanel-shadowtls-identified-in"
    for item in inbounds:
        if not isinstance(item, dict):
            continue
        if item.get("tag") in (identified_tag, identified_inner_tag, legacy_tag, legacy_inner_tag):
            continue
        if int(item.get("listen_port") or 0) == identified_port:
            raise ValueError("shadowtls_identified_port_collision")

    user_list = []
    for name, password in users:
        seed = name.encode("utf-8") + bytes([0]) + password.encode("utf-8")
        key = _shadow_b64.b64encode(
            _shadow_hmac.new(raw, seed, _shadow_hash.sha256).digest()[:16]
        ).decode("ascii")
        user_list.append({"name": name, "password": key})

    identified_inner = {
        "type": "shadowsocks",
        "tag": identified_inner_tag,
        "listen": "127.0.0.1",
        "method": "2022-blake3-aes-128-gcm",
        "password": server_key,
        "users": user_list,
    }
    identified_outer = _shadow_copy.deepcopy(outer)
    identified_outer["tag"] = identified_tag
    identified_outer["listen_port"] = identified_port
    identified_outer["detour"] = identified_inner_tag
    if not users:
        raise ValueError("shadowtls_identified_users_missing")
    for target in (identified_inner, identified_outer):
        existing = next((row for row in inbounds
                         if isinstance(row, dict) and row.get("tag") == target["tag"]), None)
        if existing is None:
            inbounds.append(target)
        else:
            if existing.get("type") != target["type"]:
                raise ValueError("shadowtls_identified_tag_conflict")
            existing.clear()
            existing.update(target)
    return identified_port
"""
